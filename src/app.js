import { initDb, getCategories, getAdaptiveQuestions, getStats } from './db.js';
import { ProgressManager } from './progress.js';

// DOM Elements
const dashboardView = document.getElementById('dashboard-view');
const quizView = document.getElementById('quiz-view');
const categoryGrid = document.getElementById('category-grid');
const questionText = document.getElementById('question-text');
const optionsGrid = document.getElementById('options-grid');
const feedbackArea = document.getElementById('feedback-area');
const feedbackStatus = document.getElementById('feedback-status');
const explanationText = document.getElementById('explanation-text');
const nextBtn = document.getElementById('next-question');
const counterText = document.getElementById('question-counter');

// Reset Modal Elements
const resetModal = document.getElementById('reset-modal');
const showResetBtn = document.getElementById('show-reset-modal');
const cancelResetBtn = document.getElementById('cancel-reset');
const confirmResetBtn = document.getElementById('confirm-reset');

let currentQuiz = [];
let currentQuestionIndex = 0;
let quizScore = 0;

async function startApp() {
    try {
        await initDb();
        renderDashboard();
        lucide.createIcons();
    } catch (err) {
        console.error("Failed to start app:", err);
        questionText.innerText = "Klarte ikke å laste databasen. Sørg for at du kjører fra en webserver.";
    }
}

function getDifficultyWeights(competence) {
    if (competence < 0.3) return { easy: 0.7, medium: 0.2, hard: 0.1 };
    if (competence < 0.7) return { easy: 0.2, medium: 0.6, hard: 0.2 };
    return { easy: 0.1, medium: 0.2, hard: 0.7 };
}

function getCompetenceLabel(score) {
    if (score < 0.3) return "Nybegynner";
    if (score < 0.7) return "Viderekommen";
    return "Ekspert";
}

function renderDashboard() {
    const categories = getCategories();
    const progress = ProgressManager.get();

    categoryGrid.innerHTML = '';

    // Calculate overall stats
    const catKeys = Object.keys(progress.categories);
    const avgCompetence = catKeys.length > 0
        ? catKeys.reduce((acc, cat) => acc + progress.categories[cat].competence, 0) / catKeys.length
        : 0;

    const totalQuizzes = progress.quizzes.length;
    const lastQuiz = progress.quizzes[totalQuizzes - 1];

    // Hero Section
    const hero = document.createElement('div');
    hero.className = 'category-card fade-in';
    hero.style.gridColumn = '1 / -1';
    hero.style.background = 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)';
    hero.style.padding = '3rem 2rem';
    hero.style.color = 'white';
    hero.style.textAlign = 'center';
    hero.style.borderColor = 'transparent';
    hero.style.display = 'flex';
    hero.style.flexDirection = 'column';
    hero.style.alignItems = 'center';

    hero.innerHTML = `
        <h2 style="font-size: 2.5rem; margin-bottom: 1rem;">Klar for teoriprøven?</h2>
        <p style="font-size: 1.1rem; opacity: 0.9; max-width: 600px; margin-bottom: 2rem;">
            Vår adaptive motor velger ut 45 spørsmål fra alle områder basert på ditt nivå.
        </p>
        
        <div style="display: flex; gap: 2rem; margin-bottom: 2.5rem; flex-wrap: wrap; justify-content: center;">
            <div class="quick-stat">
                <div style="font-size: 2rem; font-weight: 800;">${totalQuizzes}</div>
                <div style="font-size: 0.8rem; opacity: 0.8; text-transform: uppercase;">Prøver fullført</div>
            </div>
            <div class="quick-stat">
                <div style="font-size: 2rem; font-weight: 800;">${ProgressManager.getMasteredUuids().length}</div>
                <div style="font-size: 0.8rem; opacity: 0.8; text-transform: uppercase;">Spørsmål mestret</div>
            </div>
            <div class="quick-stat">
                <div style="font-size: 2rem; font-weight: 800;">${Math.round(avgCompetence * 100)}%</div>
                <div style="font-size: 0.8rem; opacity: 0.8; text-transform: uppercase;">Gjennomsnitt</div>
            </div>
        </div>

        <button id="start-main-quiz" class="next-btn" style="display: block; width: 250px; background: white; color: var(--primary); font-size: 1.2rem; height: auto; padding: 1.2rem;">
            START TEORIPRØVE
        </button>
    `;
    categoryGrid.appendChild(hero);
    document.getElementById('start-main-quiz').onclick = () => startUnifiedQuiz();

    // Stats Section
    const statsHeader = document.createElement('h3');
    statsHeader.style.gridColumn = '1 / -1';
    statsHeader.style.marginTop = '2rem';
    statsHeader.style.fontSize = '1.4rem';
    statsHeader.innerText = 'Domenestyrt Innsikt';
    categoryGrid.appendChild(statsHeader);

    categories.forEach(cat => {
        const competence = ProgressManager.getCompetence(cat);
        const percent = Math.round(competence * 100);
        const answered = Object.values(progress.answered).filter(a => a.category === cat).length;

        const card = document.createElement('div');
        card.className = 'category-card fade-in';
        card.style.cursor = 'default';
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
                <h3 style="margin: 0;">${cat}</h3>
                <span style="font-size: 0.75rem; background: var(--glass); padding: 2px 8px; border-radius: 10px; border: 1px solid var(--glass-border);">
                    ${getCompetenceLabel(competence)}
                </span>
            </div>
            <div class="stats">
                <span>Mestring</span>
                <span style="font-weight: 700; color: ${percent > 70 ? 'var(--success)' : 'white'}">${percent}%</span>
            </div>
            <div class="progress-container">
                <div class="progress-bar" style="width: ${percent}%; background: ${percent > 70 ? 'var(--success)' : 'var(--primary)'}"></div>
            </div>
            <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; justify-content: space-between;">
                <span>${answered} svar lagret</span>
            </div>
        `;
        categoryGrid.appendChild(card);
    });

    // Recent History
    if (progress.quizzes.length > 0) {
        const historyHeader = document.createElement('h3');
        historyHeader.style.gridColumn = '1 / -1';
        historyHeader.style.marginTop = '2rem';
        historyHeader.innerText = 'Siste Resultater';
        categoryGrid.appendChild(historyHeader);

        const historyList = document.createElement('div');
        historyList.style.gridColumn = '1 / -1';
        historyList.style.background = 'var(--bg-card)';
        historyList.style.borderRadius = '1rem';
        historyList.style.padding = '1rem';
        historyList.style.border = '1px solid var(--glass-border)';

        progress.quizzes.slice(-5).reverse().forEach(quiz => {
            const date = new Date(quiz.timestamp).toLocaleDateString();
            const pass = quiz.correct >= 38; // standard pass
            const item = document.createElement('div');
            item.style.display = 'flex';
            item.style.justifyContent = 'space-between';
            item.style.padding = '0.75rem';
            item.style.borderBottom = '1px solid var(--glass-border)';
            item.innerHTML = `
                <span>${date}</span>
                <span style="font-weight: 700;">${quiz.correct} / ${quiz.total}</span>
                <span style="color: ${pass ? 'var(--success)' : 'var(--error)'}; font-weight: 700;">
                    ${pass ? 'BESTÅTT' : 'IKKE BESTÅTT'}
                </span>
            `;
            historyList.appendChild(item);
        });
        categoryGrid.appendChild(historyList);
    }
}

function startUnifiedQuiz() {
    const progress = ProgressManager.get();
    const catKeys = Object.keys(progress.categories);
    const avgCompetence = catKeys.length > 0
        ? catKeys.reduce((acc, cat) => acc + progress.categories[cat].competence, 0) / catKeys.length
        : 0;

    const weights = getDifficultyWeights(avgCompetence);
    const masteredUuids = ProgressManager.getMasteredUuids();

    currentQuiz = getAdaptiveQuestions(null, weights, 45, masteredUuids);
    currentQuestionIndex = 0;
    quizScore = 0;

    dashboardView.style.display = 'none';
    quizView.style.display = 'block';

    renderQuestion();
}

function renderQuestion() {
    const q = currentQuiz[currentQuestionIndex];
    if (!q) {
        finishQuiz();
        return;
    }

    feedbackArea.classList.remove('active');
    nextBtn.style.display = 'none';
    counterText.innerText = `Spørsmål ${currentQuestionIndex + 1} / ${currentQuiz.length} (${q.difficulty})`;

    questionText.innerText = q.question;
    optionsGrid.innerHTML = '';

    [1, 2, 3, 4].forEach(i => {
        const text = q[`answer${i}`];
        if (!text) return;

        const btn = document.createElement('button');
        btn.className = 'option-btn';
        btn.innerText = text;
        btn.onclick = () => handleAnswer(i);
        optionsGrid.appendChild(btn);
    });
}

function handleAnswer(selectedIndex) {
    const q = currentQuiz[currentQuestionIndex];
    const isCorrect = selectedIndex === q.correctIndex;

    if (isCorrect) quizScore++;

    const buttons = optionsGrid.querySelectorAll('button');
    buttons.forEach((btn, idx) => {
        btn.disabled = true;
        if (idx + 1 === q.correctIndex) {
            btn.classList.add('correct');
        } else if (idx + 1 === selectedIndex) {
            btn.classList.add('wrong');
        }
    });

    ProgressManager.trackAnswer(q.uuid, q.category, q.difficulty, isCorrect);

    feedbackArea.classList.add('active');
    feedbackStatus.innerText = isCorrect ? "Riktig!" : "Feil...";
    feedbackStatus.style.color = isCorrect ? "var(--success)" : "var(--error)";
    explanationText.innerText = q.explanation;

    nextBtn.style.display = 'block';
}

nextBtn.onclick = () => {
    currentQuestionIndex++;
    if (currentQuestionIndex < currentQuiz.length) {
        renderQuestion();
    } else {
        finishQuiz();
    }
};

function finishQuiz() {
    ProgressManager.trackQuizResult(quizScore, currentQuiz.length);
    renderDashboard();
    dashboardView.style.display = 'block';
    quizView.style.display = 'none';
}

document.getElementById('back-to-dashboard').onclick = () => {
    // If we quit mid-quiz, we don't save the result
    dashboardView.style.display = 'block';
    quizView.style.display = 'none';
    renderDashboard();
};

// Reset Functionality
showResetBtn.onclick = () => {
    resetModal.classList.add('active');
};

cancelResetBtn.onclick = () => {
    resetModal.classList.remove('active');
};

confirmResetBtn.onclick = () => {
    ProgressManager.reset();
    resetModal.classList.remove('active');
    renderDashboard();
};

resetModal.onclick = (e) => {
    if (e.target === resetModal) {
        resetModal.classList.remove('active');
    }
};

startApp();
