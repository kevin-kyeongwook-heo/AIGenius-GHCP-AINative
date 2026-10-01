# AI Genius 에피소드 1: 워크숍

## "AI와 함께 코딩하기: AI-Native 워크플로우를 위한 GitHub Copilot"

환영합니다! <br>
이 Repo는 **AI Genius Episode 1** 실습을 위한 워크숍 자료입니다.<br>
이슈 작성, Copilot에게 작업 위임, 생성된 코드 리뷰, 그리고 PR 코멘트를 통한 반복(iterate)까지 AI-Native 개발 루프 전 과정을 실습하게 됩니다.

---

## 학습 목표

- 개발자에게 "AI Native"란 실제로 무엇을 의미하는지
- Copilot이 필요로 하는 컨텍스트를 담은 이슈를 작성하는 방법
- Copilot에게 작업을 할당하고 동작을 관찰하는 방법
- Copilot이 생성한 PR을 시니어 개발자처럼 리뷰하는 방법
- 처음부터 다시 시작하지 않고 PR 코멘트로 반복(iterate)하는 방법
- 코딩 과정 전반에 걸쳐 AI와 협업하기 위한 모범 사례

---

## AI-Native 워크플로우 루프

```
IDEA
  └─► GitHub Issue  (작업 내용을 설명)
       └─► Assign to Copilot  (Copilot 에이전트가 작업을 가져감)
             └─► Code is generated in a secure sandbox
                   └─► Draft PR is opened  (세션 로그와 함께)
                         └─► Human reviews and iterates via PR comments
                               └─► Merge and ship
```

이 워크플로우에서 당신의 역할은 **개발팀장** 입니다. Copilot은 *어떻게(how)* 를 처리하고, 당신은 *무엇을(what)* 그리고 *왜(why)* 를 정의합니다.

---

## 설정 안내

### 사전 준비 사항

- GitHub Copilot에 접근 가능한 GitHub 계정
- [GitHub Copilot App](https://github.com/features/copilot) 설치 (데스크톱)
- 로컬에 Python 3.10+ 설치 (starter app 실행용)
- Git 설치

### 시작하기

1. 이 Repo를 **본인 GitHub 계정**으로 **Fork** 하세요 (페이지 오른쪽 상단).

2. 포크한 Repo를 로컬에 **Clone** 하세요:
   ```bash
   git clone https://github.com/YOUR-USERNAME/AIGenius-GHCP-AINative.git
   cd AIGenius-GHCP-AINative
   ```

3. **Starter app 실행**:
   ```bash
   cd starter-app
   pip install -r requirements.txt
   python app.py add "Deploy the API" --priority high --due 2025-12-31 --tag work
   python app.py add "Buy coffee" --priority low --tag personal
   python app.py list
   python app.py search "keyword"
   python app.py stats
   ```

4. **GitHub Copilot App** 을 열고 포크한 Repo에 연결하세요.

5. [`exercises/01-write-an-issue`](./exercises/01-write-an-issue/README.md) 부터 시작하여 순서대로 실습을 진행하세요.

---

## Repo 구조

```
📁 AIGenius-GHCP-AINative/
  ├── README.md                        # 에피소드 소개 + 설정 안내
  ├── .github/
  │   ├── copilot-instructions.md      # Copilot 컨텍스트: 규칙, Azure 패턴, 비밀 값
  │   └── ISSUE_TEMPLATE/
  │       └── feature-request.md       # AI-Native 워크플로우용 이슈 템플릿
  ├── exercises/
  │   ├── 01-write-an-issue/           # 과제: 잘 작성된 이슈 작성 (클라우드/AI 옵션)
  │   ├── 02-assign-to-copilot/        # 과제: 할당 후 관찰
  │   ├── 02a-fleet-mode/              # 선택 과제: /fleet 로 병렬 하위 작업 수행
  │   ├── 02b-squad-framework/         # 선택 과제: /squad 로 지속적인 에이전트 팀 구성
  │   ├── 03-review-a-pr/              # 과제: PR 리뷰 및 코멘트 남기기
  │   ├── 04-iterate/                  # 과제: PR 코멘트로 반복하기
  │   └── 05-azure-and-ai/             # 확장 과제: Azure + OpenAI 기능을 위한 사전 작성 이슈
  └── starter-app/                     # 확장할 Python CLI 작업 관리자
      ├── app.py                       # CLI: add, list, search, complete, edit, delete, stats
      ├── requirements.txt             # click, rich, pytest
      └── tests/
         ├── conftest.py              # 공통 fixture (격리된 작업 파일)
         └── test_tasks.py            # 명령과 엣지 케이스를 검증하는 테스트
```

---

## AI-Native 코딩의 5가지 황금률

1. **더 나은 이슈 내용을 작성 (Write better issues)** -- 이슈가 곧 프롬프트입니다. 구체적으로 작성하세요.
2. **상급 개발자처럼 리뷰 (Review like a senior dev)** -- AI는 빠르게 생성하고, 사람은 똑똑하게 검증합니다.
3. **`copilot-instructions.md` 를 활용 (Use `copilot-instructions.md`)** -- 프로젝트에 대한 상시 컨텍스트를 Copilot에게 제공하세요.
4. **처음부터 다시 만들지 말고 반복 (Iterate, don't regenerate)** -- 새로 시작하는 대신 코멘트로 방향을 안내하세요.
5. **루프 안에 머물러라 (Stay in the loop)** -- 세션 로그를 확인하고 Copilot이 무엇을 왜 했는지 이해하세요.

---

## 워크숍 문서 사이트 - MkDocs

이 Repo에는 참가자용 MkDocs Material 문서 사이트가 포함되어 있습니다.

- 로컬에서 실행:
  ```bash
  pip install -r docs-requirements.txt
  mkdocs serve
  ```
- 로컬에서 빌드:
  ```bash
  mkdocs build --strict
  ```
- 배포(Deployments):
  - GitHub Actions 워크플로우 `.github/workflows/docs.yml` 은 `attendee-mkdocs-site` (그리고 `main`) 브랜치에 푸시가 발생할 때 사이트를 빌드하여 GitHub Pages에 배포합니다.
