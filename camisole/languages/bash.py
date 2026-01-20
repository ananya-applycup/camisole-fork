from camisole.models import Lang, Program


class Bash(Lang):
    source_ext = '.sh'
    interpreter = Program('bash')
    reference_source = r'''
echo 42
'''
