from codemri.analyzer import analyze


def test_java_function_labels(tmp_path):
    (tmp_path / 'Store.java').write_text('''class Store {
      String value;
      Store(String initial) { this.value = initial; }
      String read(String key) {
        String result = value + "prefix";
        // "not a literal" fakeVariable
        class Nested { String nested() { return "inner"; } }
        return result;
      }
    }''')
    graph = analyze(tmp_path)
    read = next(n for n in graph.nodes if n.name == 'read')
    assert read.details['parameters'] == ['String key']
    assert read.details['variables'] == ['result']
    assert read.details['attributes'] == ['value']
    assert read.details['strings'] == ['"prefix"']
    assert {'Store', 'String', 'Nested'} <= set(read.details['types'])
    constructor = next(n for n in graph.nodes if n.kind == 'constructor_declaration')
    assert constructor.details['attributes'] == ['value']
    assert next(n for n in graph.nodes if n.name == 'nested').details['strings'] == ['"inner"']


def test_typescript_function_labels_and_nested_ownership(tmp_path):
    (tmp_path / 'example.ts').write_text('''class Store {
      read(key: string) {
        const value = this.cache.get(key);
        function nested() { const hidden = "inner"; }
        return "outer" + value;
      }
    }
    const arrow = (input: string) => { const copy = input; return `hello ${copy}`; };
    const single = x => x.name;
    ''')
    graph = analyze(tmp_path)
    read = next(n for n in graph.nodes if n.name == 'read')
    assert read.details['parameters'] == ['key: string']
    assert read.details['variables'] == ['value']
    assert set(read.details['attributes']) == {'cache'}
    assert read.details['strings'] == ['"outer"']
    arrow = next(n for n in graph.nodes if n.name == 'arrow')
    assert arrow.details['variables'] == ['copy']
    assert arrow.details['parameters'] == ['input: string']
    assert arrow.details['strings'] == ['`hello ${copy}`']
    assert next(n for n in graph.nodes if n.name == 'single').details['parameters'] == ['x']


def test_all_call_occurrences_preserve_repeats_targets_and_nested_scope(tmp_path):
    (tmp_path / 'calls.ts').write_text('''function helper() {}
function main() {
  const emoji = "😀"; helper(); helper(); Files.createTempDirectory();
  function nested() { Files.createTempDirectory(); }
  nested();
}''')
    graph = analyze(tmp_path)
    main = next(n for n in graph.nodes if n.name == 'main')
    helper = next(n for n in graph.nodes if n.name == 'helper')
    nested = next(n for n in graph.nodes if n.name == 'nested')
    assert [c.label for c in main.call_occurrences] == ['helper', 'helper', 'Files.createTempDirectory', 'nested']
    assert [c.target_id for c in main.call_occurrences[:2]] == [helper.id, helper.id]
    assert main.call_occurrences[2].target_id is None
    assert main.call_occurrences[0].column == 22
    assert main.details['calls'] == ['helper', 'Files.createTempDirectory', 'nested']
    assert [c.label for c in nested.call_occurrences] == ['Files.createTempDirectory']


def test_java_unresolved_calls_and_constructors(tmp_path):
    (tmp_path / 'Demo.java').write_text('''class Demo {
      static void main() { Files.createTempDirectory("a"); Files.createTempDirectory("b"); new Demo(); }
    }''')
    main = next(n for n in analyze(tmp_path).nodes if n.name == 'main')
    assert [c.label for c in main.call_occurrences] == ['Files.createTempDirectory', 'Files.createTempDirectory', 'new Demo']
    assert len({c.column for c in main.call_occurrences}) == 3
