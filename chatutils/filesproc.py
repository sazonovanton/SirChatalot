#!/usr/bin/env python3
'''
Class for converting PDF, DOC, DOCX, PPT, PPTX, TXT files to just a plain text.
'''
import configparser
config = configparser.ConfigParser()
config.read('./data/.config', encoding='utf-8')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-FilesProc")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7,
                                       encoding='utf-8')
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import PyPDF2
from docx import Document
from pptx import Presentation
import os
from sys import platform
platform = platform.lower()
if platform == 'win32':
    # pip install comtypes
    import comtypes
elif platform == 'linux':
    # sudo apt install catdoc -y
    import subprocess
else:
    logger.error(f'Error (platform): {platform} is not supported.')
    exit(1)

class FilesProc:
    def __init__(self) -> None:
        # path where files are stored
        self.path = './data/files'
        self.delete_after_processing = config.getboolean('Files', 'DeleteAfterProcessing') if config.has_option('Files', 'DeleteAfterProcessing') else True
        self.platform = platform

    async def delete_file(self, filepath) -> bool:
        # delete file that was processed
        try:
            os.remove(filepath)
            return True
        except OSError as e:
            logger.error(f'Error (delete file): {e.filename} - {e.strerror}.')
            return False
        except Exception as e:
            logger.error(f'Error (delete file): {e}.')
            return False
        
    async def extract_text(self, filepath) -> str:
        '''
        Extract text from file
        Selects a method based on the file extension
        '''
        # create absolute path for file from relative path
        filepath = os.path.abspath(filepath)
        try:
            if filepath.endswith('.pdf'):
                text = await self.extract_text_from_pdf(filepath)
            elif filepath.endswith('.docx'):
                text = await self.extract_text_from_docx(filepath)
            elif filepath.endswith('.doc'):
                text = await self.extract_text_from_doc(filepath)
            elif filepath.endswith('.pptx'):
                text = await self.extract_text_from_pptx(filepath)
            elif filepath.endswith('.ppt'):
                text = await self.extract_text_from_ppt(filepath)
            elif filepath.endswith('.txt'):
                with open(filepath, 'r') as f:
                    text = f.read()
            else:
                return ''
            # delete file after processing
            if self.delete_after_processing:
                await self.delete_file(filepath)
            return text
        except Exception as e:
            logger.error(f'Error (extract text): {e}.')
            return ''
        
    async def extract_text_from_pdf(self, filepath) -> str:
        '''
        Extract text from PDF file
        '''
        pdf_file_obj = open(filepath, 'rb')
        pdf_reader = PyPDF2.PdfReader(pdf_file_obj)
        page_obj = pdf_reader.pages[0]
        text = page_obj.extract_text()
        pdf_file_obj.close()
        return text
    
    async def extract_text_from_docx(self, filepath) -> str:
        '''
        Extract text from DOCX file
        '''
        doc = Document(filepath)
        full_text = []

        # Extract text from paragraphs
        for para in doc.paragraphs:
            full_text.append(para.text)

        full_text.append('\n### Tables: ###')
        
        # Extract text from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text.append(cell.text)

        return '\n'.join(full_text)
    
    async def extract_text_from_doc(self, filepath) -> str:
        '''
        Extract text from DOC file
        '''
        doc_text = ''
        if self.platform == 'win32':
            word = comtypes.client.CreateObject('Word.Application')
            doc = word.Documents.Open(filepath)
            doc_text = doc.Content.Text
            doc.Close()
            word.Quit()
        if self.platform == 'linux':
            command = ['catdoc', filepath]
            doc_text = subprocess.check_output(command, universal_newlines=True)
        return doc_text
    
    async def extract_text_from_pptx(self, filepath) -> str:
        '''
        Extract text from PPTX file
        '''
        prs = Presentation(filepath)
        full_text = []

        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    full_text.append(shape.text)
                if hasattr(shape, "table"):
                    for row in shape.table.rows:
                        for cell in row.cells:
                            for paragraph in cell.text_frame.paragraphs:
                                for run in paragraph.runs:
                                    full_text.append(run.text)
                if hasattr(shape, "group_items"):
                    for item in shape.group_items:
                        if item.has_text_frame:
                            for paragraph in item.text_frame.paragraphs:
                                for run in paragraph.runs:
                                    full_text.append(run.text)
                            
        return '\n'.join(full_text)
    
    async def extract_text_from_ppt(self, filepath) -> str:
        '''
        Extract text from PPT file
        '''
        ppt_text = ''
        if self.platform == 'win32':
            powerpoint = comtypes.client.CreateObject('Powerpoint.Application')
            powerpoint.Visible = 1
            ppt = powerpoint.Presentations.Open(filepath)
            full_text = []
            for slide in ppt.Slides:
                for shape in slide.Shapes:
                    if hasattr(shape, 'TextFrame'):
                        full_text.append(shape.TextFrame.TextRange.Text)
            ppt.Close()
            powerpoint.Quit()
            ppt_text = '\n'.join(full_text)
        if self.platform == 'linux':
            command = ['catppt', filepath]
            ppt_text = subprocess.check_output(command, universal_newlines=True)
        return ppt_text
    
    async def get_files(self) -> list:
        '''
        Get list of files in the directory
        '''
        files = []
        for file in os.listdir(self.path):
            if os.path.isfile(os.path.join(self.path, file)):
                files.append(file)
        return files
    
    async def delete_all(self) -> bool:
        '''
        Delete all files in the directory
        '''
        try:
            for file in os.listdir(self.path):
                if os.path.isfile(os.path.join(self.path, file)):
                    os.remove(os.path.join(self.path, file))
            return True
        except Exception as e:
            logger.error(f'Error (delete all): {e}.')
            return False

    async def main(self) -> None:
        '''
        Main function for testing
        '''
        files = await self.get_files()
        for file in files:
            text = await self.extract_text(os.path.join(self.path, file))
            print(text)
            print('---------------------')
        

if __name__ == '__main__':
    filesproc = FilesProc()
    asyncio.run(filesproc.main())
