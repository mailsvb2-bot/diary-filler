"""Clinical input normalization without fabricated medical facts."""
from medical_models import parse_admission_occurrence_value,strip_admission_occurrence_prefix,PatientData
from medical_parser_work import MedicalParserWorkMixin
from medical_renderer_special import MedicalRendererSpecialMixin
from docx import Document
from medical_docx_editor import DocxBlockEditor

def test_occurrence():
    for text, expected in (
        ("впервые добровольно", "первично"),
        ("в первый раз самостоятельно", "первично"),
        ("первично добровольно, повторно", "повторно"),
        ("добровольно, вторично", "повторно"),
        ("обычное описание", ""),
    ):
        assert parse_admission_occurrence_value(text)==expected
        stripped=strip_admission_occurrence_prefix(text)
        assert not any(term in stripped.lower() for term in
            ("впервые", "в первый раз", "первично", "повторно", "вторично"))

def test_work():
    assert MedicalParserWorkMixin._split_work_position_value(
        'ООО «Ромашка», бухгалтер')==('ООО «Ромашка»','бухгалтер')
    assert MedicalParserWorkMixin._split_work_position_value(
        'ООО «Ромашка»')==('ООО «Ромашка»','')

def test_vk_headings():
    doc=Document()
    doc.add_paragraph("ЭПИКРИЗ № 1")
    editor=DocxBlockEditor(doc)
    MedicalRendererSpecialMixin._normalize_vk_visible_labels(editor, PatientData())
    assert "ЭПИКРИЗ № 1" not in [p.text for p in doc.paragraphs]
    assert "ЭПИКРИЗ" in [p.text for p in doc.paragraphs]
    doc=Document()
    doc.add_paragraph("ЭПИКРИЗ № 1")
    editor=DocxBlockEditor(doc)
    MedicalRendererSpecialMixin._normalize_vk_visible_labels(
        editor, PatientData(vk_epicrisis_number="7"))
    assert "ЭПИКРИЗ № 7" in [p.text for p in doc.paragraphs]

if __name__=="__main__":
    test_occurrence()
    test_work()
    test_vk_headings()
    print("MEDICAL SOURCE CORRECTIONS: PASS")
