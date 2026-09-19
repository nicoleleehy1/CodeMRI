from codemri.analyzer import analyze


def test_java_methods_cross_file_call_chain_and_filenames(tmp_path):
    (tmp_path/'Engine.java').write_text('''public class Engine {
      private Journal journal;
      public Engine(Journal journal) { this.journal = journal; }
      public void write(String value) { journal.append(value); maybeFlush(); }
      private void maybeFlush() { flush(); }
      private void flush() { journal.clear(); }
    }''')
    (tmp_path/'Journal.java').write_text('''public class Journal {
      public void append(String value) { persist(value); }
      private void persist(String value) { }
      public void clear() { }
    }''')
    graph=analyze(tmp_path)
    nodes={s.id:s for s in graph.nodes}
    calls={(nodes[e.source].name,nodes[e.target].name) for e in graph.edges if e.kind=='calls'}
    assert {('write','append'),('write','maybeFlush'),('maybeFlush','flush'),('flush','clear'),('append','persist')}<=calls
    write=next(s for s in graph.nodes if s.name=='write')
    assert write.signature=='write(String value)'
    assert write.start_line==4
    assert any(n['name']=='Engine.java' for n in graph.layers['modules']['nodes'])
    assert all('/' not in n['name'] for n in graph.layers['modules']['nodes'])


def test_same_arity_overload_not_guessed_and_comments_not_calls(tmp_path):
    (tmp_path/'Example.java').write_text('''public class Example {
      void run() { overloaded(1); /* fake(); */ real(); }
      void overloaded(int x) {} void overloaded(String x) {}
      void fake() {} void real() {}
    }''')
    graph=analyze(tmp_path);nodes={n.id:n for n in graph.nodes}
    calls=[nodes[e.target].name for e in graph.edges if e.kind=='calls']
    assert calls==['real']
    assert any('overload' in warning for warning in graph.warnings)


def test_renaming_source_changes_graph_no_fixed_repo_nodes(tmp_path):
    file=tmp_path/'Original.java'
    file.write_text('public class Original { void alpha() { beta(); } void beta() {} }')
    first=analyze(tmp_path)
    file.write_text('public class Original { void gamma() { delta(); } void delta() {} }')
    second=analyze(tmp_path)
    assert first.revision!=second.revision
    assert {'gamma','delta'}<={n.name for n in second.nodes}
    assert not {'alpha','beta'}&{n.name for n in second.nodes}
