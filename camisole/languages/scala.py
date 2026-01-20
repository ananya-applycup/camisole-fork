from camisole.models import Lang, Program

class Scala(Lang):
    source_ext = '.scala'
    interpreter = Program('bash')
    reference_source = r'object Main extends App { println(42) }'

    def get_execute_cmd(self, source):
        # requires: JDK + scalac + scala
        # Compile to class files, then run Main
        return ['bash', '-lc', f'scalac "{source}" && scala Main']
