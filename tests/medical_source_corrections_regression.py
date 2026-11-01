from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

    doc = Document()
    doc.add_paragraph("Зам. гл. врача Зуйкова  А.А.")
    MedicalRendererSpecialMixin._normalize_vk_visible_labels(
        DocxBlockEditor(doc), PatientData())
    assert "Заместитель главного врача Зуйкова А.А." in [p.text for p in doc.paragraphs]

def test_service_boundaries_and_real_docx():
    from tempfile import TemporaryDirectory
    from docx import Document
    from pathlib import Path
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from generation_performance_profile import _make_fixture
    with TemporaryDirectory() as t:
        nav, service, data = _make_fixture(Path(t))
        data.expert_sick_leave_from = ""
        data.sick_leave = "нужен с 15.06.2026"
        created, normalized = service.create_documents(
            navigation_path=nav, output_dir=Path(t)/"vk",
            selected_docs=["sick_leave_vk"], override_data=data)
        assert len(created) == 1
        assert normalized.expert_sick_leave_from == "15.06.2026"
        data.rvk_referral_present = "нет"
        try:
            service.create_documents(
                navigation_path=nav, output_dir=Path(t)/"rvk",
                selected_docs=["primary", "rvk"], override_data=data)
        except ValueError as exc:
            assert "противоречит" in str(exc)
        else:
            raise AssertionError("Contradictory RVK package accepted")

    with TemporaryDirectory() as t:
        nav, service, data = _make_fixture(Path(t))
        data.somatic_status = "Соматический осмотр\\nВторая строка осмотра"
        data.diagnosis = "F99.9 Подтвержденный диагноз\\nДополнительный диагноз"
        created, _ = service.create_documents(
            navigation_path=nav, output_dir=Path(t)/"discharge",
            selected_docs=["discharge"], override_data=data)
        paragraphs = [p.text for p in Document(created[0]).paragraphs]
        sidx = next(i for i,x in enumerate(paragraphs)
                    if x.startswith("Сомато-неврологический статус:"))
        didx = next(i for i,x in enumerate(paragraphs)
                    if x.startswith("Диагноз:"))
        assert sidx < didx
        assert "Вторая строка осмотра" in "\\n".join(paragraphs[sidx:didx])
        assert "Дополнительный диагноз" in paragraphs[didx]


def test_nested_diary_discovery():
    from tempfile import TemporaryDirectory
    from docx import Document
    from diary_template_discovery import DiaryTemplateDiscoveryMixin
    from diary_text_selection import folder_has_diary_text_candidates
    with TemporaryDirectory() as t:
        root = Path(t)
        reader = DiaryTemplateDiscoveryMixin()
        reader._diary_template_files_cache = {}
        assert reader._iter_diary_template_docx_files(root) == []
        new_file = root / "Октябрь" / "15.docx"
        new_file.parent.mkdir()
        Document().save(new_file)
        assert new_file in reader._iter_diary_template_docx_files(root)
        texts = root / "Тексты" / "Месяц" / "01.docx"
        texts.parent.mkdir(parents=True)
        Document().save(texts)
        assert folder_has_diary_text_candidates(root / "Тексты")


if __name__=="__main__":
    test_occurrence()
    test_work()
    test_vk_headings()
    test_service_boundaries_and_real_docx()
    test_nested_diary_discovery()
    print("MEDICAL SOURCE CORRECTIONS: PASS")
