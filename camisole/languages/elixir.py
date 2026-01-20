from camisole.models import Lang, Program

class Elixir(Lang):
    source_ext = '.exs'
    interpreter = Program('elixir')
    reference_source = r'IO.puts("42")'

    def get_execute_cmd(self, source):
        # requires: elixir (and erlang runtime)
        return ['elixir', source]
