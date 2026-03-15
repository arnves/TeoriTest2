/**
 * Handles localStorage for student progress.
 */
const PROGRESS_KEY = 'teoritest_progress';

export const ProgressManager = {
    get() {
        const stored = localStorage.getItem(PROGRESS_KEY);
        let data = stored ? JSON.parse(stored) : null;

        // Default state if nothing stored
        if (!data) {
            data = {
                answered: {},
                categories: {},
                quizzes: []
            };
        }

        // Migration for early versions
        if (!data.quizzes) data.quizzes = [];
        if (!data.answered) data.answered = {};
        if (!data.categories) data.categories = {};

        return data;
    },

    save(progress) {
        localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
    },

    trackAnswer(questionUuid, category, difficulty, isCorrect) {
        const progress = this.get();

        // Tracking per question
        if (!progress.answered[questionUuid]) {
            progress.answered[questionUuid] = {
                history: [],
                category: category,
                difficulty: difficulty,
                mastered: false
            };
        }

        const qData = progress.answered[questionUuid];
        qData.history.push(isCorrect);

        // Keep last 5 results per question
        if (qData.history.length > 5) qData.history.shift();

        // Identify mastery: 3 consecutive correct
        const last3 = qData.history.slice(-3);
        if (last3.length === 3 && last3.every(x => x === true)) {
            qData.mastered = true;
        } else {
            qData.mastered = false;
        }

        // Domain-specific competence (rolling average of last 15 questions in category)
        if (!progress.categories[category]) {
            progress.categories[category] = { history: [], competence: 0 };
        }

        const catData = progress.categories[category];
        catData.history.push(isCorrect);

        const ROLLING_WINDOW_SIZE = 15;
        if (catData.history.length > ROLLING_WINDOW_SIZE) {
            catData.history.shift();
        }

        const successCount = catData.history.filter(x => x).length;
        catData.competence = successCount / catData.history.length;

        this.save(progress);
    },

    getMasteredUuids() {
        const progress = this.get();
        return Object.keys(progress.answered).filter(uuid => progress.answered[uuid].mastered);
    },

    trackQuizResult(correct, total) {
        const progress = this.get();
        progress.quizzes.push({
            timestamp: Date.now(),
            correct,
            total
        });
        // Keep last 50 quizzes
        if (progress.quizzes.length > 50) progress.quizzes.shift();
        this.save(progress);
    },

    getCompetence(category) {
        const progress = this.get();
        if (!progress.categories[category]) return 0;
        return progress.categories[category].competence || 0;
    },

    reset() {
        localStorage.removeItem(PROGRESS_KEY);
    }
};
