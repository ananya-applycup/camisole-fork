from camisole.models import Lang, Program

class Go(Lang):
    source_ext = '.go'
    interpreter = Program('bash')
    reference_source = r'package main; import "fmt"; func main(){ fmt.Println(42) }'

    def get_execute_cmd(self, source):
        # requires: go
        return ['bash', '-lc', f'go build -o main "{source}" && ./main']
