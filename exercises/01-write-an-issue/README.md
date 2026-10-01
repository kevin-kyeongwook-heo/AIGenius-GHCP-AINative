# Exercise 01 -- 잘 작성된 이슈(Issue) 만들기

## 목표 (Goal)

Copilot이 고품질 코드를 생성하는 데 필요한 컨텍스트를 담은 GitHub Issue 작성 방법을 익힙니다.

## 왜 중요한가 (Why This Matters)

AI-Native 워크플로우에서는 이슈가 곧 프롬프트입니다. Copilot이 만들어내는 결과물의 품질은 여러분이 작성한 이슈의 품질과 직결됩니다. 모호한 이슈는 모호한 코드를 낳고, 구체적이고 잘 구조화된 이슈와 명확한 수용 기준(acceptance criteria)은 여러분의 의도에 훨씬 잘 부합하는 코드를 만들어냅니다.

**핵심 인사이트:** 여러분은 단순히 사람 팀원에게 작업을 설명하는 것이 아닙니다. AI 에이전트가 곧바로 해석하고 실행하게 될 명세(specification)를 작성하는 것입니다.

---

## AI-Native 이슈를 잘 작성하는 요소 (What Makes a Good AI-Native Issue)

Copilot을 위해 잘 작성된 이슈에는 다음 요소가 포함됩니다:

| 섹션 | 목적 |
|---|---|
| **Problem statement** | 어떤 공백이나 문제점을 해결하려 하는가? |
| **Desired behaviour** | 완료 시 사용자가 무엇을 할 수 있어야 하는가? |
| **Acceptance criteria** | "완료(done)"를 정의하는 조건 체크리스트 |
| **Constraints** | 사용할 라이브러리, 피해야 할 것, 성능 요구 사항 |
| **Definition of Done** | 최종 검증용 체크리스트 |

---

## 실습 과제 (Your Task)

1. 이 Repo의 **Issues** 탭으로 이동합니다.
   **Issues** 탭이 안보이는 경우 Github Repository 페이지 상단 메뉴 **Settings** 의 **General** 페이지에서 **Features** > **Issues** 체크박스를 Enable 한다.
3. **New issue** 를 클릭하고 **Feature Request** 템플릿을 선택합니다.
4. 다음 기능 중 하나에 대한 이슈를 작성하세요:

   **Option A:** 태스크 저장소를 Azure Table Storage로 마이그레이션
   > 현재 이 앱은 태스크를 로컬 JSON 파일에 저장합니다. 저장 계층(storage layer)을 Azure Table Storage로 마이그레이션하여 태스크를 클라우드에 영속화하세요. `azure-data-tables` 를 사용하고 자격 증명은 환경 변수에서 로드합니다. CLI 명령들은 현재와 동일하게 동작해야 합니다.

   **Option B:** Azure OpenAI 기반 태스크 카테고리 분류 추가
   > 사용자가 태스크를 추가할 때 Azure OpenAI를 호출하여 카테고리(예: "work", "personal", "health")를 자동으로 제안하고, 태그가 제공되지 않았다면 그것을 태그로 설정합니다. 사용자는 `--no-ai` 로 이 기능을 끌 수 있어야 합니다. 자격 증명은 환경 변수에서 로드합니다.

   **Option C:** `search` 명령 추가
   > 사용자는 `python app.py search "keyword"` 를 실행하여 이름 또는 설명에 해당 키워드가 포함된 태스크를 찾을 수 있어야 합니다. 결과는 우선순위(높은 순)로 정렬되며 매칭된 텍스트가 강조 표시되어야 합니다.

   **Option D:** 반복(recurring) 태스크 추가
   > 사용자는 `--repeat daily|weekly|monthly` 로 태스크를 반복 태스크로 표시할 수 있어야 합니다. 반복 태스크가 완료되면 다음 마감일이 계산된 새 복사본이 자동으로 생성되어야 합니다.

5. 템플릿의 **모든 섹션**을 채우세요. 빈 섹션이 남지 않도록 하세요.
6. 이슈를 제출합니다.

---

## 확인사항

- "완료"를 명확히 기술하기 위해 얼마나 구체적으로 작성해야 했나요?
- 만약 진짜 사람 팀원이라면 이미 알고 있을 만한 정보 중에서 Copilot에게는 어떤 정보가 추가로 필요했나요?
- 수용조건(acceptance criteria)을 작성하면서 기능에 대한 본인의 생각이 더 명확해졌나요?

---

## 다음 단계 (Next Step)

이슈 작성을 성공했다면 [Exercise 02 -- Assign to Copilot](../02-assign-to-copilot/README.md) 으로 이동하세요.
