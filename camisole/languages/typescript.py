from camisole.models import Lang, Program

class TypeScript(Lang):
    source_ext = '.ts'
    interpreter = Program('bash')
    # minimal TS that prints 42
    reference_source = r"console.log(42);"

    def get_execute_cmd(self, source):
        # compile to main.js then run
        # requires: node + tsc
        return [
            'bash', '-lc',
            f'tsc "{source}" --target ES2020 --module commonjs --outFile main.js && node main.js'
        ]
