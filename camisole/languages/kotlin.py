from camisole.models import Lang, Program


class Kotlin(Lang):
    source_ext = '.kt'
    compiler = Program('kotlinc', opts=['-include-runtime', '-d', 'main.jar'])
    interpreter = Program('java', opts=['-jar', 'main.jar'])
    reference_source = r'''
fun main() {
    println(42)
}
'''
