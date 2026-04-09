from app.chat.llm import _build_system_prompt, _build_user_prompt
from app.chat.models import ProjectCatalogEntry
from app.schemas.chat import Citation


def test_system_prompt_explicitly_forbids_outside_knowledge_and_inference():
    prompt = _build_system_prompt()

    assert "Do not use outside knowledge" in prompt
    assert "Never infer exact scores, dates, fees" in prompt
    assert "Do not add typical or likely values" in prompt


def test_user_prompt_requires_no_typical_value_guessing_when_evidence_is_generic():
    prompt = _build_user_prompt(
        question="帝国理工 AI 硕士的雅思要求是什么",
        question_type="field",
        primary_project=ProjectCatalogEntry(
            school_slug="imperial",
            school_name="Imperial College London",
            program_slug="msc-artificial-intelligence",
            program_name="MSc Artificial Intelligence",
            degree_type="MSc",
        ),
        comparison_project=None,
        citations=[
            Citation(
                school_name="Imperial College London",
                program_name="MSc Artificial Intelligence",
                page_title="Artificial Intelligence MSc | Study | Imperial College London",
                source_url="https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                evidence_text="For admission to this course, you must achieve the higher university requirement in the appropriate English language qualification.",
                evidence_type="structured_field",
            )
        ],
    )

    assert "If the evidence does not state an exact value, say that the exact value could not be confirmed" in prompt
    assert "Respond in the user's language when saying that an exact value could not be confirmed" in prompt
    assert "Do not write words such as usually, typically, generally, often, 一般, 通常" in prompt
