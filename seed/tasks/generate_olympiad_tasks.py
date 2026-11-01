"""Usage: python3 generate_olympiad_tasks.py seed/tasks/olympiad

Generate draft packages for the olympiad problem bank (ОТ-01, Q-13).

The statements are original drafts by Claude Code, not copies of external problems
(Q-05); a coach approves them before students see them. Expected outputs come from
straightforward Python implementations; the C++ reference solutions are checked
against them separately.
"""

import heapq
import json
import random
import sys
from collections import deque
from pathlib import Path

OUT = Path(sys.argv[1])
rng = random.Random(20261101)
NOTE = (
    "Олимпиада есептер банкінің жобасы (Q-13): шарты, тесттері, эталон шешімі мен талдауы "
    "Claude Code дайындаған, жаттықтырушы тексеріп бекітуі керек."
)
III = {"knowledge_actions": 2, "algorithm_freedom": 2, "edge_cases": 1, "justification": 1}
IV = {"knowledge_actions": 2, "algorithm_freedom": 2, "edge_cases": 2, "justification": 1}


def write(key, title, topic, level, features, rationale, rating, tags, statement, inp, outp,
          editorial, solution, tests, public=("01", "02"), memory_kb=262144, time_ms=1000,
          subtasks=None, subtask_points=None):
    d = OUT / key
    (d / "tests").mkdir(parents=True, exist_ok=True)
    config = {
        "key": key,
        "title": title,
        "level": level,
        "features": features,
        "level_rationale": rationale,
        "topic": topic,
        "tags": tags,
        "cf_rating": rating,
        "time_limit_ms": time_ms,
        "memory_limit_kb": memory_kb,
        "reference_language": "cpp17",
        "public_tests": list(public),
        "source_note": NOTE,
    }
    if subtasks:
        config["subtasks"] = subtasks
        config["subtask_points"] = subtask_points
    (d / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    (d / "statement.md").write_text(f"# {title}\n\n{statement.strip()}\n")
    (d / "input.md").write_text(inp.strip() + "\n")
    (d / "output.md").write_text(outp.strip() + "\n")
    (d / "editorial.md").write_text(editorial.strip() + "\n")
    (d / "solution.cpp").write_text(solution.strip() + "\n")
    for i, (data, answer) in enumerate(tests, start=1):
        (d / "tests" / f"{i:02d}.in").write_text(data)
        (d / "tests" / f"{i:02d}.out").write_text(answer)


def lines(*rows):
    return "".join(" ".join(map(str, r)) + "\n" for r in rows)


# 4.1.1 Binary search on the answer -----------------------------------------------------------


def machines(k, times):
    lo, hi = 0, min(times) * k
    while lo < hi:
        mid = (lo + hi) // 2
        if sum(mid // t for t in times) >= k:
            hi = mid
        else:
            lo = mid + 1
    return lo


def machines_tests():
    cases = [(5, [2, 3]), (1, [7]), (10, [1, 1, 1]), (1000000000, [1000000000]), (7, [3, 5, 9, 2])]
    for _ in range(4):
        n = rng.randint(1, 1000)
        cases.append((rng.randint(1, 10**9), [rng.randint(1, 10**9) for _ in range(n)]))
    return [(lines((len(t), k), t), f"{machines(k, t)}\n") for k, t in cases]


write(
    "OLY-4.1.1-1", "Станоктар", "4.1.1", "III", III,
    "Жауап бойынша екілік іздеу; шекараны дұрыс таңдау және 64 биттік сандар керек.",
    1400, ["binary search"],
    """
Цехта $n$ станок бар. $i$-ші станок бір бөлшекті дәл $t_i$ секундта жасайды және
бөлшектерді бірінен соң бірін үзіліссіз жасай береді. Барлық станок бір мезетте іске
қосылады. Барлығы кемінде $k$ бөлшек дайын болатын ең аз уақытты табыңыз.
""",
    "Бірінші жолда $n$ және $k$ ($1 \\le n \\le 10^5$, $1 \\le k \\le 10^9$). Екінші жолда "
    "$n$ сан $t_i$ ($1 \\le t_i \\le 10^9$).",
    "Бір бүтін сан — ең аз уақыт (секунд).",
    """
Уақыт $T$ ішінде барлығы $\\sum \\lfloor T / t_i \\rfloor$ бөлшек жасалады; бұл $T$ бойынша
кемімейтін функция, сондықтан жауапты екілік іздеумен табамыз. Жоғарғы шек —
$\\min t_i \\cdot k$ (ең жылдам станоктың өзі жеткілікті). Шек $10^{18}$-ге жетеді:
`long long` керек, ал қосындыны $k$-ден асқанда тоқтатқан жөн. Күрделілігі
$O(n \\log(\\min t \\cdot k))$.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    int n; long long k;
    cin >> n >> k;
    vector<long long> t(n);
    for (auto &x : t) cin >> x;
    long long lo = 0, hi = *min_element(t.begin(), t.end()) * k;
    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2, made = 0;
        for (long long x : t) { made += mid / x; if (made >= k) break; }
        if (made >= k) hi = mid; else lo = mid + 1;
    }
    cout << lo << "\n";
}
""",
    machines_tests(),
)


# 4.1.2 Sieve of Eratosthenes ---------------------------------------------------------------


LIMIT = 10**6
_sieve = bytearray([1]) * (LIMIT + 1)
_sieve[0] = _sieve[1] = 0
for _i in range(2, int(LIMIT**0.5) + 1):
    if _sieve[_i]:
        _sieve[_i * _i :: _i] = bytearray(len(range(_i * _i, LIMIT + 1, _i)))
_prefix = [0] * (LIMIT + 1)
for _i in range(1, LIMIT + 1):
    _prefix[_i] = _prefix[_i - 1] + _sieve[_i]


def primes_tests():
    cases = [[(1, 10), (11, 20)], [(1, 1), (2, 2)], [(1, LIMIT)], [(999983, 1000000), (4, 4)]]
    for _ in range(4):
        q = []
        for _ in range(rng.randint(1, 2000)):
            a, b = sorted((rng.randint(1, LIMIT), rng.randint(1, LIMIT)))
            q.append((a, b))
        cases.append(q)
    return [
        (lines((len(q),), *q), "".join(f"{_prefix[b] - _prefix[a - 1]}\n" for a, b in q))
        for q in cases
    ]


write(
    "OLY-4.1.2-1", "Аралықтағы жай сандар", "4.1.2", "III", III,
    "Эратосфен елегі мен префикс қосындылар; сұраулар көп болғанда әрқайсысын жеке "
    "тексеру уақытқа сыймайды.",
    1200, ["number theory", "sieve", "prefix sums"],
    """
$q$ сұрау берілген. Әр сұрауда $[l, r]$ аралығында неше жай сан бар екенін табыңыз.
""",
    "Бірінші жолда $q$ ($1 \\le q \\le 2 \\cdot 10^5$). Келесі $q$ жолда $l$ және $r$ "
    "($1 \\le l \\le r \\le 10^6$).",
    "Әр сұрауға бір жол — жай сандар саны.",
    """
Бір рет $10^6$-ға дейін Эратосфен елегін құрып, $p_i$ — $i$-ден аспайтын жай сандар
санын есептейміз. Сұраудың жауабы $p_r - p_{l-1}$. Елек $O(N \\log \\log N)$, әр сұрау
$O(1)$. Жад шектеуі қатаң (64 МБ): `vector<int>` пен `vector<char>` жеткілікті.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    const int N = 1000000;
    vector<char> composite(N + 1, 0);
    vector<int> pref(N + 1, 0);
    composite[0] = composite[1] = 1;
    for (int i = 2; (long long)i * i <= N; ++i)
        if (!composite[i])
            for (int j = i * i; j <= N; j += i) composite[j] = 1;
    for (int i = 1; i <= N; ++i) pref[i] = pref[i - 1] + !composite[i];
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int q; cin >> q;
    while (q--) { int l, r; cin >> l >> r; cout << pref[r] - pref[l - 1] << "\n"; }
}
""",
    primes_tests(),
    memory_kb=65536,
)


# 4.1.2 Binary exponentiation ---------------------------------------------------------------


def power_tests():
    cases = [[(2, 10, 1000)], [(5, 0, 7), (0, 0, 13)], [(7, 10**18, 1)], [(10**9, 10**18, 10**9 + 7)]]
    for _ in range(4):
        cases.append(
            [
                (rng.randint(0, 10**9), rng.randint(0, 10**18), rng.randint(1, 10**9))
                for _ in range(rng.randint(1, 1000))
            ]
        )
    return [(lines((len(q),), *q), "".join(f"{pow(a, b, m)}\n" for a, b, m in q)) for q in cases]


write(
    "OLY-4.1.2-2", "Үлкен дәреже", "4.1.2", "III", III,
    "Екілік дәрежелеу; $0^0$, $m = 1$ және көбейтудегі толып кету — шеттік жағдайлар.",
    1300, ["number theory", "binary exponentiation", "modular arithmetic"],
    """
$q$ сұрау берілген. Әр сұрауда $a^b \\bmod m$ мәнін табыңыз. $0^0 = 1$ деп есептеледі.
""",
    "Бірінші жолда $q$ ($1 \\le q \\le 10^5$). Келесі $q$ жолда $a$, $b$, $m$ "
    "($0 \\le a \\le 10^9$, $0 \\le b \\le 10^{18}$, $1 \\le m \\le 10^9$).",
    "Әр сұрауға бір жол — $a^b \\bmod m$.",
    """
$a^b$ мәнін $b$-ның екілік жазбасы бойынша есептейміз: $a^{2k} = (a^k)^2$,
$a^{2k+1} = a \\cdot a^{2k}$. Бұл $O(\\log b)$ көбейту. Көбейтінді $10^{18}$-ге дейін
жетеді, сондықтан `long long` керек. $m = 1$ болса жауап 0 (нәтижені соңында да
$m$ бойынша алу керек).
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int q; cin >> q;
    while (q--) {
        long long a, m; unsigned long long b;
        cin >> a >> b >> m;
        long long r = 1 % m; a %= m;
        while (b) { if (b & 1) r = r * a % m; a = a * a % m; b >>= 1; }
        cout << r << "\n";
    }
}
""",
    power_tests(),
)


# 4.1.3 Linear DP ---------------------------------------------------------------------------


MOD = 10**9 + 7


def stairs(n, k, broken):
    bad = set(broken)
    dp = [0] * (n + 1)
    dp[0] = 1
    window = 1
    for i in range(1, n + 1):
        dp[i] = 0 if i in bad else window % MOD
        window += dp[i]
        if i - k >= 0:
            window -= dp[i - k]
        window %= MOD
    return dp[n]


def stairs_tests():
    cases = [(4, 2, []), (5, 3, [2]), (1, 1, []), (10, 1, []), (6, 2, [3, 4])]
    for _ in range(4):
        n = rng.randint(1, 10**5)
        k = rng.randint(1, n)
        broken = sorted(rng.sample(range(1, n), min(n - 1, rng.randint(0, 50))))
        cases.append((n, k, broken))
    return [
        (lines((n, k, len(b)), b), f"{stairs(n, k, b)}\n") for n, k, b in cases
    ]


write(
    "OLY-4.1.3-1", "Сынық баспалдақ", "4.1.3", "III", III,
    "Сызықтық динамика және жылжымалы қосынды; тікелей $O(nk)$ шешім уақытқа сыймайды.",
    1500, ["dp", "prefix sums"],
    """
Баспалдақ $n$ сатыдан тұрады, адам 0-сатыда тұр. Бір қадамда ол $1$-ден $k$-ға дейін
сатыға көтеріле алады. Кейбір сатылар сынық, оларға аяқ басуға болмайды. $n$-сатыға
жетудің неше тәсілі бар? Жауапты $10^9 + 7$ бойынша шығарыңыз.
""",
    "Бірінші жолда $n$, $k$, $b$ ($1 \\le k \\le n \\le 10^5$, $0 \\le b < n$). Екінші "
    "жолда сынық сатылардың $b$ нөмірі (өсу ретімен, әрқайсысы $1$ мен $n$ аралығында). "
    "$b = 0$ болса, екінші жол бос.",
    "Бір сан — тәсілдер саны $10^9 + 7$ бойынша.",
    """
$dp_i$ — $i$-сатыға жету тәсілдері: сынық сатыда 0, әйтпесе
$dp_i = dp_{i-1} + \\dots + dp_{i-k}$. Соңғы $k$ мәннің қосындысын жылжымалы терезе ретінде
сақтасақ, $O(n)$. Модуль бойынша азайтқанда теріс сан шықпауын қадағалаңыз.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    const long long MOD = 1000000007;
    int n, k, b; cin >> n >> k >> b;
    vector<char> bad(n + 1, 0);
    for (int i = 0; i < b; ++i) { int x; cin >> x; bad[x] = 1; }
    vector<long long> dp(n + 1, 0);
    dp[0] = 1;
    long long window = 1;
    for (int i = 1; i <= n; ++i) {
        dp[i] = bad[i] ? 0 : window;
        window = (window + dp[i]) % MOD;
        if (i - k >= 0) window = (window - dp[i - k] + MOD) % MOD;
    }
    cout << dp[n] << "\n";
}
""",
    stairs_tests(),
)


# 4.1.3 Knapsack ----------------------------------------------------------------------------


def knapsack(w, items):
    best = [0] * (w + 1)
    for weight, value in items:
        for c in range(w, weight - 1, -1):
            best[c] = max(best[c], best[c - weight] + value)
    return best[w]


def knapsack_tests():
    cases = [(10, [(5, 10), (4, 40), (6, 30), (3, 50)]), (1, [(2, 5)]), (5, [(5, 7), (5, 8)])]
    for _ in range(5):
        n = rng.randint(1, 100)
        w = rng.randint(1, 10**5)
        cases.append((w, [(rng.randint(1, w), rng.randint(1, 10**9)) for _ in range(n)]))
    return [(lines((len(it), w), *it), f"{knapsack(w, it)}\n") for w, it in cases]


write(
    "OLY-4.1.3-2", "Жорыққа рюкзак", "4.1.3", "IV", IV,
    "0/1 рюкзак: күйді таңдау, бір өлшемді массивпен жадты үнемдеу (16 МБ), 64 биттік "
    "қосынды.",
    1600, ["dp", "knapsack"],
    """
Жорыққа $n$ зат алуға болады: $i$-ші заттың салмағы $w_i$, пайдасы $v_i$. Рюкзак ең көбі
$W$ салмақты көтереді. Әр затты бір рет қана алуға болады. Пайданың ең үлкен қосындысын
табыңыз.
""",
    "Бірінші жолда $n$ және $W$ ($1 \\le n \\le 100$, $1 \\le W \\le 10^5$). Келесі $n$ "
    "жолда $w_i$ және $v_i$ ($1 \\le w_i \\le 10^5$, $1 \\le v_i \\le 10^9$).",
    "Бір сан — пайданың ең үлкен қосындысы.",
    """
$best_c$ — салмағы $c$-дан аспайтын заттардың ең үлкен пайдасы. Заттарды бір-бірлеп
қосамыз да, $c$-ны $W$-дан кемімелі ретпен жүреміз: сонда әр зат бір рет қана алынады.
$O(nW)$ уақыт, $O(W)$ жад; екі өлшемді кесте ($100 \\cdot 10^5$ сан) 16 МБ-қа сыймайды.
Қосынды $10^{11}$-ге жетеді — `long long`.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    int n, W; cin >> n >> W;
    vector<long long> best(W + 1, 0);
    for (int i = 0; i < n; ++i) {
        int w; long long v; cin >> w >> v;
        for (int c = W; c >= w; --c) best[c] = max(best[c], best[c - w] + v);
    }
    cout << best[W] << "\n";
}
""",
    knapsack_tests(),
    memory_kb=16384,
)


# 4.1.4 BFS ---------------------------------------------------------------------------------


def maze(grid):
    h, w = len(grid), len(grid[0])
    start = next((r, c) for r in range(h) for c in range(w) if grid[r][c] == "S")
    dist = {start: 0}
    queue = deque([start])
    while queue:
        r, c = queue.popleft()
        if grid[r][c] == "F":
            return dist[(r, c)]
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and grid[nr][nc] != "#" and (nr, nc) not in dist:
                dist[(nr, nc)] = dist[(r, c)] + 1
                queue.append((nr, nc))
    return -1


def random_maze(h, w, walls):
    cells = [["#" if rng.random() < walls else "." for _ in range(w)] for _ in range(h)]
    sr, sc, fr, fc = rng.randrange(h), rng.randrange(w), rng.randrange(h), rng.randrange(w)
    while (fr, fc) == (sr, sc):
        fr, fc = rng.randrange(h), rng.randrange(w)
    cells[sr][sc], cells[fr][fc] = "S", "F"
    return ["".join(r) for r in cells]


def maze_tests():
    cases = [["S.#", "..#", "#.F"], ["S#F"], ["SF"], ["S..", "###", "..F"]]
    cases += [random_maze(rng.randint(2, 50), rng.randint(2, 50), 0.25) for _ in range(2)]
    cases += [random_maze(1000, 1000, 0.2), random_maze(300, 300, 0.45)]
    return [(lines((len(g), len(g[0]))) + "".join(r + "\n" for r in g), f"{maze(g)}\n") for g in cases]


write(
    "OLY-4.1.4-1", "Лабиринт", "4.1.4", "III", III,
    "Кесте түріндегі графта ендеп іздеу; жолы жоқ жағдай және $10^6$ төбе.",
    1500, ["graphs", "bfs", "shortest paths"],
    """
Лабиринт $h \\times w$ кестемен берілген: `.` — бос тор, `#` — қабырға, `S` — бастау,
`F` — шығу. Бір қадамда көрші торға (жоғары, төмен, солға, оңға) өтуге болады. `S`-тен
`F`-ке дейінгі ең аз қадам санын табыңыз. Жол болмаса, `-1` шығарыңыз.
""",
    "Бірінші жолда $h$ және $w$ ($1 \\le h, w \\le 1000$). Келесі $h$ жолда $w$ таңба. "
    "`S` пен `F` дәл бір реттен кездеседі.",
    "Бір сан — қадамдар саны немесе `-1`.",
    """
Әр тор — төбе, көрші бос торлар — қабырғалар. Салмақсыз графтағы ең қысқа жол ендеп
іздеумен (BFS) табылады: кезектен шыққан тордың қашықтығы ең аз. $O(hw)$. Рекурсивті
тереңдеп іздеу мұнда ең қысқа жолды бермейді және $10^6$ төбеде стекті толтырады.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int h, w; cin >> h >> w;
    vector<string> g(h);
    for (auto &row : g) cin >> row;
    vector<int> dist(h * w, -1);
    queue<int> q;
    for (int i = 0; i < h * w; ++i)
        if (g[i / w][i % w] == 'S') { dist[i] = 0; q.push(i); }
    int dr[] = {1, -1, 0, 0}, dc[] = {0, 0, 1, -1};
    while (!q.empty()) {
        int v = q.front(); q.pop();
        int r = v / w, c = v % w;
        if (g[r][c] == 'F') { cout << dist[v] << "\n"; return 0; }
        for (int d = 0; d < 4; ++d) {
            int nr = r + dr[d], nc = c + dc[d];
            if (nr < 0 || nr >= h || nc < 0 || nc >= w || g[nr][nc] == '#') continue;
            int u = nr * w + nc;
            if (dist[u] == -1) { dist[u] = dist[v] + 1; q.push(u); }
        }
    }
    cout << -1 << "\n";
}
""",
    maze_tests(),
)


# 4.2.2 Disjoint set union ------------------------------------------------------------------


def dsu_answers(n, edges):
    parent = list(range(n + 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    comps, out = n, []
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            comps -= 1
        out.append(comps)
    return out


def dsu_tests():
    cases = [(4, [(1, 2), (3, 4), (1, 3)]), (3, [(1, 1), (2, 3), (3, 2)]), (1, [(1, 1)])]
    for n, m in ((10, 15), (1000, 2000), (200000, 200000), (50000, 30000)):
        cases.append((n, [(rng.randint(1, n), rng.randint(1, n)) for _ in range(m)]))
    return [
        (lines((n, len(e)), *e), "".join(f"{x}\n" for x in dsu_answers(n, e))) for n, e in cases
    ]


write(
    "OLY-4.2.2-1", "Жолдар салу", "4.2.2", "III", III,
    "Қиылыспайтын жиындар жүйесі; жол қысқарту мен біріктіру эвристикасы $O(\\alpha(n))$ "
    "береді.",
    1500, ["dsu", "graphs"],
    """
Елде $n$ қала бар, басында олардың арасында жол жоқ. Бірінен соң бірі $m$ жол салынады:
әр жол екі қаланы екі бағытта байланыстырады. Әр жол салынғаннан кейін байланысқан
аймақтар (бір-біріне жолмен жетуге болатын қалалар топтары) санын шығарыңыз.
""",
    "Бірінші жолда $n$ және $m$ ($1 \\le n, m \\le 2 \\cdot 10^5$). Келесі $m$ жолда "
    "$a_i$ және $b_i$ ($1 \\le a_i, b_i \\le n$) — жаңа жол салынған қалалар.",
    "$m$ жол — әр жол салынғаннан кейінгі аймақтар саны.",
    """
Аймақтарды қиылыспайтын жиындар жүйесімен (DSU) сақтаймыз. Жол екі түрлі жиынды
байланыстырса, оларды біріктіріп, аймақтар санын бірге азайтамыз. Жол қысқарту мен
өлшем бойынша біріктіру әр операцияны іс жүзінде $O(1)$ етеді. Бір қаланы өзімен
байланыстыратын жол санды өзгертпейді.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
vector<int> parent, sz;
int find(int x) { while (parent[x] != x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; }
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, m; cin >> n >> m;
    parent.resize(n + 1); sz.assign(n + 1, 1);
    iota(parent.begin(), parent.end(), 0);
    int comps = n;
    while (m--) {
        int a, b; cin >> a >> b;
        a = find(a); b = find(b);
        if (a != b) {
            if (sz[a] < sz[b]) swap(a, b);
            parent[b] = a; sz[a] += sz[b]; --comps;
        }
        cout << comps << "\n";
    }
}
""",
    dsu_tests(),
)


# 4.2.2 Priority queue, IOI subtasks --------------------------------------------------------


def kth_answers(k, values):
    heap, out = [], []
    for v in values:
        heapq.heappush(heap, v)
        if len(heap) > k:
            heapq.heappop(heap)
        out.append(heap[0] if len(heap) == k else -1)
    return out


def kth_tests():
    small = [(2, [5, 1, 7, 3]), (1, [4, 4, 2]), (3, [1, 2])]
    small += [(rng.randint(1, 50), [rng.randint(1, 10**9) for _ in range(rng.randint(1, 1000))])]
    big = [
        (rng.randint(1, 1000), [rng.randint(1, 10**9) for _ in range(200000)]),
        (30000, [rng.randint(1, 10**9) for _ in range(60000)]),
        (1, list(range(60000, 0, -1))),
    ]
    return [
        (lines((len(v), k), v), "".join(f"{x}\n" for x in kth_answers(k, v)))
        for k, v in small + big
    ]


write(
    "OLY-4.2.2-2", "Жарыстағы k-шы орын", "4.2.2", "IV", IV,
    "Бинарлық үйме: $k$ ең үлкен мәнді ғана сақтау; сұрыптаудан тиімдірек шешімді "
    "негіздеу керек (IOI ішкі есептері).",
    1600, ["heap", "data structures"],
    """
Жарыстың нәтижелері бірінен соң бірі келеді: әр жаңа нәтиже — бүтін балл. Әр нәтиже
келгеннен кейін қазіргі $k$-шы ең үлкен баллды шығарыңыз. Нәтиже әзірге $k$-дан аз болса,
`-1` шығарыңыз.

**Ішкі есептер.** 1-ішкі есеп (30 балл): $n \\le 1000$. 2-ішкі есеп (70 балл):
$n \\le 2 \\cdot 10^5$.
""",
    "Бірінші жолда $n$ және $k$ ($1 \\le k \\le n \\le 2 \\cdot 10^5$). Екінші жолда $n$ "
    "балл ($1 \\le a_i \\le 10^9$).",
    "$n$ жол — әр нәтижеден кейінгі $k$-шы ең үлкен балл немесе `-1`.",
    """
Әр жолы барлық нәтижені сұрыптау $O(n^2 \\log n)$ — тек 1-ішкі есепке жетеді. $k$ ең
үлкен баллды минимумы жоғарыда тұратын үймеде (`priority_queue` with `greater`)
сақтаймыз: жаңа балл қосылып, үйме $k$-дан асса, ең кішісі шығарылады. Сонда $k$-шы
ең үлкен балл — үйменің төбесі. Күрделілігі $O(n \\log k)$.
""",
    r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, k; cin >> n >> k;
    priority_queue<long long, vector<long long>, greater<long long>> top;
    for (int i = 0; i < n; ++i) {
        long long a; cin >> a;
        top.push(a);
        if ((int)top.size() > k) top.pop();
        cout << ((int)top.size() == k ? top.top() : -1) << "\n";
    }
}
""",
    kth_tests(),
    subtasks={"01": 1, "02": 1, "03": 1, "04": 1, "05": 2, "06": 2, "07": 2},
    subtask_points={"1": 30, "2": 70},
)
