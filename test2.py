import os
from pyhtml2pdf import converter
from problem_list import problem_list


for chapter in problem_list.keys():
    for i, id in enumerate(problem_list[chapter]):
        path = os.path.abspath(f'data/{chapter}/{id}.html')
        pdf_dir = os.path.join(os.path.dirname(path), 'pdf')
        os.makedirs(pdf_dir, exist_ok=True)
        converter.convert(f'file:///{path}', os.path.join(pdf_dir, f'{id}.pdf'))