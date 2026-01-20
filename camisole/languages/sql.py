from camisole.models import Lang, Program

class Sqlite(Lang):
    source_ext = '.sql'
    interpreter = Program('bash')
    reference_source = r'SELECT 42;'

    def get_execute_cmd(self, source):
        # requires: sqlite3
        # Executes SQL script; prints results to stdout
        return ['bash', '-lc', f'sqlite3 :memory: < "{source}"']
