from codemri.analyzer import analyze


def test_repository_packages_files_and_symbol_ownership(tmp_path):
    package = tmp_path / 'src' / 'store'
    package.mkdir(parents=True)
    (package / 'store.ts').write_text('''export interface Reader { key: string; read(input: string): string; }
    export class Store implements Reader {
      key: string = "start";
      constructor(key: string) { this.key = key; }
      read(input: string): string {
        const local = input;
        function nested() { return "nested"; }
        nested();
        return local;
      }
    }
    type Key = string;
    enum Status { Ready, Busy }
    const LIMIT = 5;
    let globalValue = 0;
    function standalone() { return 1; }
    ''')
    graph = analyze(tmp_path)
    nodes = {n['id']: n for n in graph.layers['hierarchy']['nodes']}
    symbols = {n.name: n for n in graph.nodes if n.kind != 'module'}
    assert nodes['repository:root']['name'] == tmp_path.name
    store = nodes[symbols['Store'].id]
    file = nodes[store['parent']]
    package = nodes[file['parent']]
    component = nodes[package['parent']]
    assert (store['kind'], file['kind'], package['kind'], component['kind']) == ('class_declaration', 'file', 'package', 'component')
    assert package['name'] == 'src/store'
    assert nodes[symbols['read'].id]['parent'] == store['id']
    assert nodes[symbols['nested'].id]['parent'] == symbols['read'].id
    assert nodes[symbols['standalone'].id]['parent'] == file['id']
    assert symbols['LIMIT'].kind == 'constant'
    assert symbols['globalValue'].kind == 'global_variable'
    assert symbols['Status'].kind == 'enum_declaration'
    assert symbols['Reader'].details['attributes'] == ['key: string']
    assert symbols['Reader'].details['methods'] == ['read(input: string): string']
    assert symbols['Store'].details['constructors'] == ['constructor(key: string)']
    assert symbols['read'].details['nested'] == ['nested']
    assert symbols['read'].details['calls'] == ['nested']
    assert symbols['read'].details['returns'] == ['Type: string', 'local']
    assert all(edge['source'] in nodes and edge['target'] in nodes for edge in graph.layers['hierarchy']['edges'])
    # Reanalysis must follow source changes, never a saved demo graph.
    (tmp_path / 'extra.ts').write_text('export function added() { return 7; }')
    updated = analyze(tmp_path)
    assert any(n.name == 'added' for n in updated.nodes)
    assert any(n['name'] == 'extra.ts' for n in updated.layers['files']['nodes'])


def test_java_class_and_interface_members_are_not_flattened(tmp_path):
    (tmp_path / 'Service.java').write_text('''public class Service {
      private String name;
      public Service(String name) { this.name = name; }
      public String read() { return name; }
      class Nested { void inside() {} }
    }
    interface Reader { String read(String key); }
    ''')
    graph = analyze(tmp_path)
    service = next(n for n in graph.nodes if n.name == 'Service' and n.kind == 'class_declaration')
    assert service.details['attributes'] == ['name: String']
    assert service.details['constructors'] == ['Service(String name)']
    assert service.details['methods'] == ['read(): String']
    interface = next(n for n in graph.nodes if n.name == 'Reader')
    assert interface.details['methods'] == ['read(String key): String']
    nodes = {n['id']: n for n in graph.layers['hierarchy']['nodes']}
    nested = next(n for n in graph.nodes if n.name == 'Nested')
    inside = next(n for n in graph.nodes if n.name == 'inside')
    assert nodes[nested.id]['parent'] == service.id
    assert nodes[inside.id]['parent'] == nested.id


def test_unclassified_files_stay_in_repository_hierarchy(tmp_path):
    (tmp_path / 'README.md').write_text('Reference')
    (tmp_path / 'Main.java').write_text('public class Main { void run() {} }')
    graph = analyze(tmp_path)
    assert {p for n in graph.layers['files']['nodes'] for p in n['paths']} == {'README.md', 'Main.java'}


def test_architecture_resources_are_source_backed(tmp_path):
    (tmp_path / 'server.ts').write_text('''const app = express();
    app.get("/items", handler);
    // app.post("/fake", handler);
    ''')
    (tmp_path / 'schema.sql').write_text('CREATE TABLE items (id INTEGER);')
    (tmp_path / 'compose.yaml').write_text('services:\n  events:\n    image: rabbitmq:3\n')
    graph = analyze(tmp_path)
    nodes = graph.layers['repository']['nodes']
    assert any(n['kind'] == 'api_endpoint' and n['name'] == 'GET /items' for n in nodes)
    assert not any('/fake' in n['name'] for n in nodes)
    assert any(n['kind'] == 'database_entity' and n['name'] == 'items' for n in nodes)
    assert any(n['kind'] == 'event_queue' and n['name'] == 'events' for n in nodes)
    assert all(n['evidence'] for n in nodes if n['kind'] in {'api_endpoint', 'database_entity', 'event_queue'})
