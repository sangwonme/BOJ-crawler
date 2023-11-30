import os
from pyhtml2pdf import converter
import time
import PyPDF2

def get_all_paths(chapter, problem_list):
    dir = f'data/{chapter}/pdf'
    paths = [os.path.join(dir, 'title.pdf')]
    for i, id in enumerate(problem_list[chapter]):
        paths.append(os.path.join(dir, f'{id}.pdf'))
    return paths

def merge_pdfs(paths, output):
    pdf_writer = PyPDF2.PdfWriter()

    memo_path = 'data/memo.pdf'
    memo_page = PyPDF2.PdfReader(memo_path)
    def add_memo_page(num):
        for _ in range(num):
            pdf_writer.add_page(memo_page.pages[0])

    for i, path in enumerate(paths):
        pdf_reader = PyPDF2.PdfReader(path)
        for page in range(len(pdf_reader.pages)):
            pdf_writer.add_page(pdf_reader.pages[page])
        # add memo pages
        if i == 0: #title
            add_memo_page(3)
        else:
            add_memo_page(1)

    with open(output, 'wb') as out:
        pdf_writer.write(out)

def save_pdf(problem_list):
    init_time = time.time()
    for chapter in problem_list.keys():
        path = os.path.abspath(f'data/{chapter}/title.html')
        pdf_dir = os.path.join(os.path.dirname(path), 'pdf')
        os.makedirs(pdf_dir, exist_ok=True)
        converter.convert(f'file:///{path}', os.path.join(pdf_dir, 'title.pdf'))
        for i, id in enumerate(problem_list[chapter]):
            start_time = time.time()
            path = os.path.abspath(f'data/{chapter}/{id}.html')
            pdf_dir = os.path.join(os.path.dirname(path), 'pdf')
            os.makedirs(pdf_dir, exist_ok=True)
            converter.convert(f'file:///{path}', os.path.join(pdf_dir, f'{id}.pdf'))
            time_duration = time.time() - start_time
            print(f'Saved : {chapter} - {id} pdf. ({round(time_duration,2)} sec.)')
    print(round(time.time()-init_time, 2), 'sec.')

def convert(problem_list, filename):
    save_pdf(problem_list)
    pdf_paths = []
    for chapter in problem_list.keys():
        pdf_paths += get_all_paths(chapter, problem_list)
    merge_pdfs(pdf_paths, filename)