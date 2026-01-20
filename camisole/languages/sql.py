from camisole.models import Lang, Program


class Sqlite(Lang):
    source_ext = '.sql'
    interpreter = Program('sqlite3', opts=[':memory:'])
    reference_source = r'''
SELECT 42;
'''
