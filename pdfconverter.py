import os
from pyhtml2pdf import converter
from problem_list import problem_list
import time

def convert():
    init_time = time.time()
    for chapter in problem_list.keys():
        for i, id in enumerate(problem_list[chapter]):
            start_time = time.time()
            path = os.path.abspath(f'data/{chapter}/{id}.html')
            pdf_dir = os.path.join(os.path.dirname(path), 'pdf')
            os.makedirs(pdf_dir, exist_ok=True)
            converter.convert(f'file:///{path}', os.path.join(pdf_dir, f'{id}.pdf'))
            time_duration = time.time() - start_time
            print(f'Saved : {chapter} - {id} pdf. ({round(time_duration,2)} sec.)')
    print(round(time.time()-init_time, 2), 'sec.')

if __name__ == "__main__":
    convert()