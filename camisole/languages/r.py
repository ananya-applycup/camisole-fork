from camisole.models import Lang, Program


class R(Lang):
    source_ext = '.R'
    interpreter = Program('Rscript')
    reference_source = r'''
cat("42\n")
'''
