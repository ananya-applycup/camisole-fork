from camisole.models import Lang, Program


class Scala(Lang):
    source_ext = '.scala'
    compiler = Program('scalac')
    interpreter = Program('scala', opts=['Main'])
    reference_source = r'''
object Main extends App {
  println(42)
}
'''
