---
description: Professional GitHub Workflow for Fitness OS
---

# GitHub Workflow Rules for Fitness OS

Follow these steps for every new feature, bug fix, or refactor.

## 1. Branch Strategy
- **main**: Stable production branch. No direct commits allowed.
- **feature/**: New features (e.g., `feature/food-parser`).
- **fix/**: Bug fixes (e.g., `fix/google-fit-auth`).
- **refactor/**: Code improvements (e.g., `refactor/dashboard-queries`).
- **chore/**: Maintenance (e.g., `chore/update-deps`).
- **docs/**: Documentation changes.

## 2. Development Process

1. **Update Local main**:
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create Branch**:
   ```bash
   git checkout -b <branch-type>/<shorthand-description>
   ```

3. **Implement & Test**:
   - Follow project structure.
   - Keep secrets in `.env` (excluded by git).
   - Verify locally with `streamlit run app/app.py`.

4. **Commit (Conventional)**:
   ```bash
   git add .
   git commit -m "type: description"
   ```
   *Types: feat, fix, refactor, chore, docs, style, test.*

5. **Push & PR**:
   - Push branch: `git push origin <branch-name>`
   - Inform the user to create/review a Pull Request.
   - Merge only after review (prefer Squash and Merge).

## 3. Structure & Quality
- No loose files in root (except README, .gitignore, requirements.txt, .env).
- Pull Requests should be < 400 lines.
- No hardcoded secrets.
