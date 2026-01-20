from camisole.models import Lang, Program

class Swift(Lang):
    source_ext = '.swift'
    interpreter = Program('bash')
    reference_source = r'import Foundation; print(42)'

    def get_execute_cmd(self, source):
        # requires: swift toolchain (swiftc) on Linux
        return ['bash', '-lc', f'swiftc "{source}" -O -o main && ./main']
