from __future__ import annotations

from app.chat.models import ChatQuestionAnalysis

COMPARE_KEYWORDS = (
    "compare",
    "comparison",
    "difference",
    "different",
    "相比",
    "比较",
    "差别",
    "区别",
    "和上一个比",
    "和刚才那个比",
)

FOLLOW_UP_MARKERS = (
    "它",
    "这个",
    "那",
    "上一",
    "上一个",
    "刚才",
    "前一个",
    "that",
    "it",
)

FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tuition": ("tuition", "fee", "fees", "cost", "学费", "费用", "多少钱", "收费"),
    "application_deadline": (
        "deadline",
        "closing date",
        "截止",
        "ddl",
        "申请时间",
        "什么时候截止",
    ),
    "language_requirement": (
        "ielts",
        "toefl",
        "english",
        "language requirement",
        "雅思",
        "托福",
        "英语",
        "语言要求",
    ),
    "academic_requirement": (
        "academic requirement",
        "entry requirement",
        "admission requirement",
        "requirements",
        "gpa",
        "honours",
        "学术要求",
        "背景要求",
        "本科要求",
        "均分",
        "成绩要求",
    ),
    "duration": ("duration", "study length", "多久", "几年", "学制", "读几年", "多长时间"),
    "department": ("department", "faculty", "学院", "系", "院系"),
}

EXPLANATORY_KEYWORDS = (
    "overview",
    "introduce",
    "introduction",
    "learn",
    "study",
    "module",
    "modules",
    "curriculum",
    "course",
    "courses",
    "介绍",
    "学什么",
    "主要学",
    "课程",
    "课程设置",
    "特点",
    "官网怎么介绍",
)


class QuestionUnderstandingService:
    def understand(self, question: str) -> ChatQuestionAnalysis:
        normalized = _normalize_text(question)
        question_type = "explanatory"
        field_names = self._detect_field_names(normalized)

        if any(keyword in normalized for keyword in COMPARE_KEYWORDS):
            question_type = "comparison"
        elif field_names:
            question_type = "field"
        elif any(keyword in normalized for keyword in EXPLANATORY_KEYWORDS):
            question_type = "explanatory"

        return ChatQuestionAnalysis(
            question_type=question_type,
            field_names=field_names,
            is_follow_up=_is_follow_up(normalized),
        )

    def _detect_field_names(self, normalized_question: str) -> list[str]:
        detected: list[str] = []
        for field_name, keywords in FIELD_KEYWORDS.items():
            if any(keyword in normalized_question for keyword in keywords):
                detected.append(field_name)
        return detected


def _is_follow_up(normalized_question: str) -> bool:
    if not normalized_question:
        return False
    if normalized_question.startswith(FOLLOW_UP_MARKERS):
        return True
    return any(f" {marker}" in normalized_question for marker in FOLLOW_UP_MARKERS if len(marker) > 1)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())
