from camisole.models import Lang, Program


class Dart(Lang):
    source_ext = '.dart'
    interpreter = Program('dart', opts=['run'])
    reference_source = r'''
void main() {
  print('42');
}
'''
