from camisole.models import Lang, Program

class Dart(Lang):
    source_ext = '.dart'
    interpreter = Program('bash')
    reference_source = r'void main(){ print("42"); }'

    def get_execute_cmd(self, source):
        # requires: dart SDK
        return ['bash', '-lc', f'dart run "{source}"']
