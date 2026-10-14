"""Create exactly three synthetic Colombian documents for live acceptance tests."""
import argparse
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import reportlab
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE = (595, 842)
DISCLAIMER = 'DOCUMENTO SINTÉTICO DE PRUEBA - Sin datos de personas reales.'
CASES = {
    '01_imagenes_escaneado.pdf': [
        'MEDIFLOW - PRUEBA DE ACEPTACIÓN COLOMBIA',
        'INFORME DE RESONANCIA MAGNÉTICA',
        'Especialidad: Radiología', 'Prioridad: Rutina', 'Fecha: 11/10/2026', '',
        'PACIENTE', 'Andrea Prueba Imagen', 'DOCUMENTO', 'C.C. 1.099.900.101',
        'Edad: 35 años', '',
        'ESTUDIO: Resonancia magnética de rodilla derecha.',
        'HALLAZGOS: Meniscos de morfología conservada.',
        'Ligamentos cruzados íntegros. Sin derrame articular.',
        'CONCLUSIÓN: Estudio sin alteraciones estructurales.', '',
        'Firma y Sello del Médico', 'Dra. Marcela Prueba Radiología',
        'Registro médico: 900101', 'C.C. 52.900.101', '', DISCLAIMER],
    '02_urgencias_ocr.png': [
        'MEDIFLOW - PRUEBA DE ACEPTACIÓN COLOMBIA', 'ORDEN DE LABORATORIO',
        'Especialidad: Laboratorio', 'Prioridad: Urgente', 'Fecha: 11/10/2026', '',
        'PACIENTE', 'Carlos Prueba Urgencia', 'DOCUMENTO', 'C.C. 1.099.900.102',
        'Edad: 42 años', '',
        'PRUEBA SOLICITADA: Hemograma completo.',
        'Se requiere evaluación urgente en la atención actual.', '',
        'Firma y Sello del Médico', 'Dr. Felipe Prueba Medicina',
        'Registro médico: 900102', 'C.C. 79.900.102', '', DISCLAIMER],
    '03_revision_humana.pdf': [
        'MEDIFLOW - PRUEBA DE ACEPTACIÓN COLOMBIA', 'FÓRMULA MÉDICA',
        'Especialidad: Medicina general', 'Prioridad: Rutina', 'Fecha: 11/10/2026', '',
        'PACIENTE', 'Luisa Prueba Revisión', 'DOCUMENTO', 'C.C. 1.099.900.103',
        'Edad: 29 años', '',
        'MEDICAMENTO: Acetaminofén.', 'DOSIS: 500 mg.', 'VÍA: oral.', '',
        'Firma y Sello del Médico', 'Dra. Diana Prueba Medicina',
        'Registro médico: 900103', 'C.C. 52.900.103', '', DISCLAIMER],
}


def render(lines):
    image = Image.new('RGB', (1785, 2526), 'white')
    draw = ImageDraw.Draw(image)
    # ReportLab bundles a Unicode font; Pillow's default font lacks accents.
    font = str(Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf')
    body = ImageFont.truetype(font, size=30)
    heading = ImageFont.truetype(font, size=35)
    y = 150
    for index, line in enumerate(lines):
        draw.text((135, y), line, font=heading if index < 2 else body, fill='black')
        y += 68 if index < 2 else 61
    return image


def generate(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for filename, lines in CASES.items():
        path = directory / filename
        if filename.endswith('.png'):
            render(lines).save(path, dpi=(216, 216))
        elif 'escaneado' in filename:
            image = render(lines)
            pdf = canvas.Canvas(str(path), pagesize=PAGE)
            pdf.drawImage(ImageReader(image), 0, 0, width=PAGE[0], height=PAGE[1])
            pdf.save()
        else:
            pdf = canvas.Canvas(str(path), pagesize=PAGE)
            pdf.setFont('Helvetica', 11)
            y = 795
            for line in lines:
                pdf.drawString(38, y, line)
                y -= 23
            pdf.save()
        print(filename)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    generate(parser.parse_args().directory)
