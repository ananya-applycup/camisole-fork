from camisole.models import Lang, Program

class Julia(Lang):
    source_ext = '.jl'
    interpreter = Program('julia')
    reference_source = r'println(42)'

    def get_execute_cmd(self, source):
        # requires: julia
        return ['julia', source]
