from camisole.models import Lang, Program


class Elixir(Lang):
    source_ext = '.exs'
    interpreter = Program('elixir')
    reference_source = r'''
IO.puts(42)
'''
