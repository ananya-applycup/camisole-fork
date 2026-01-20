from camisole.models import Lang, Program


class TypeScript(Lang):
    source_ext = '.ts'
    compiler = Program('tsc', opts=[
        '--target', 'ES2020',
        '--module', 'commonjs',
        '--outFile', 'main.js',
    ])
    interpreter = Program('node')
    reference_source = r'''
console.log(42);
'''
