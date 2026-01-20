from camisole.models import Lang, Program


class Swift(Lang):
    source_ext = '.swift'
    compiler = Program('swiftc', opts=['-O', '-o', 'main'])
    interpreter = Program('./main')
    reference_source = r'''
import Foundation

print(42)
'''
