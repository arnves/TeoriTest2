/**
 * Handles database loading and querying using sql.js
 */

let db = null;

export async function initDb() {
    if (db) return db;

    const sqlPromise = initSqlJs({
        locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}`
    });

    const dataPromise = fetch('public/teoriprove.db').then(res => res.arrayBuffer());

    const [SQL, buf] = await Promise.all([sqlPromise, dataPromise]);
    db = new SQL.Database(new Uint8Array(buf));
    return db;
}

export function getCategories() {
    if (!db) return [];
    const res = db.exec("SELECT DISTINCT category FROM questions");
    return res[0].values.map(v => v[0]);
}

export function getQuestionsByCategory(category, limit = 10, difficulty = null) {
    if (!db) return [];

    let query = `SELECT * FROM questions WHERE category = ?`;
    let params = [category];

    if (difficulty) {
        query += ` AND difficulty = ?`;
        params.push(difficulty);
    }

    query += ` ORDER BY RANDOM() LIMIT ?`;
    params.push(limit);

    const res = db.exec(query, params);
    if (res.length === 0) return [];

    const columns = res[0].columns;
    return res[0].values.map(row => {
        const obj = {};
        columns.forEach((col, i) => obj[col] = row[i]);
        return obj;
    });
}

/**
 * Fetches a mix of questions based on target distributions.
 */
export function getAdaptiveQuestions(category, weights, totalLimit = 15, excludeList = []) {
    if (!db) return [];

    let allSelected = [];
    const difficulties = ['easy', 'medium', 'hard'];

    // Prepare exclusion string for SQL
    const excludeStr = excludeList.length > 0 ? excludeList.map(u => `'${u}'`).join(',') : '';
    const excludeQuery = excludeStr ? `AND uuid NOT IN (${excludeStr})` : '';

    difficulties.forEach(diff => {
        const count = Math.round(totalLimit * weights[diff]);
        if (count > 0) {
            let query = category
                ? `SELECT * FROM questions WHERE category = ? AND difficulty = ? ${excludeQuery} ORDER BY RANDOM() LIMIT ?`
                : `SELECT * FROM questions WHERE difficulty = ? ${excludeQuery} ORDER BY RANDOM() LIMIT ?`;
            let params = category ? [category, diff, count] : [diff, count];

            let res = db.exec(query, params);

            // Fallback: If not enough unmastered questions, fill with any questions
            if (res.length === 0 || (res[0].values.length < count)) {
                const alreadyGot = res.length > 0 ? res[0].values.length : 0;
                const needed = count - alreadyGot;

                let fallbackQuery = category
                    ? `SELECT * FROM questions WHERE category = ? AND difficulty = ? ORDER BY RANDOM() LIMIT ?`
                    : `SELECT * FROM questions WHERE difficulty = ? ORDER BY RANDOM() LIMIT ?`;
                let fallbackParams = category ? [category, diff, needed] : [diff, needed];

                const fallbackRes = db.exec(fallbackQuery, fallbackParams);
                if (fallbackRes.length > 0) {
                    if (res.length === 0) res = fallbackRes;
                    else res[0].values = res[0].values.concat(fallbackRes[0].values);
                }
            }

            if (res.length > 0) {
                const columns = res[0].columns;
                const rows = res[0].values.map(row => {
                    const obj = {};
                    columns.forEach((col, i) => obj[col] = row[i]);
                    return obj;
                });
                allSelected = allSelected.concat(rows);
            }
        }
    });

    return allSelected.sort(() => Math.random() - 0.5).slice(0, totalLimit);
}

export function getStats() {
    if (!db) return {};
    const res = db.exec("SELECT category, COUNT(*) as total FROM questions GROUP BY category");
    const stats = {};
    if (res.length > 0) {
        res[0].values.forEach(v => {
            stats[v[0]] = { total: v[1] };
        });
    }
    return stats;
}
