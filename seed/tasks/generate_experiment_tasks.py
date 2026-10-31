"""Usage: python3 generate_experiment_tasks.py seed/tasks/experiment

Generate draft packages for the 9 experiment tasks (seed/tasks/experiment/*).

Expected outputs come from straightforward Python implementations; the C++ reference
solutions are then checked against them separately.
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

OUT = Path(sys.argv[1])
rng = random.Random(20261031)


def odd_even(n):
    return "EVEN" if n % 2 == 0 else "ODD"


def is_pal(s):
    return s == s[::-1]


def can_swap_pal(s):
    if is_pal(s):
        return True
    chars = list(s)
    for i in range(len(chars)):
        for j in range(i + 1, len(chars)):
            chars[i], chars[j] = chars[j], chars[i]
            if chars[0] != "0" and is_pal("".join(chars)):
                return True
            chars[i], chars[j] = chars[j], chars[i]
    return False


def next_greater(s):
    d = list(s)
    i = len(d) - 2
    while i >= 0 and d[i] >= d[i + 1]:
        i -= 1
    if i < 0:
        return "-1"
    j = len(d) - 1
    while d[j] <= d[i]:
        j -= 1
    d[i], d[j] = d[j], d[i]
    d[i + 1 :] = reversed(d[i + 1 :])
    return "".join(d)


def most_frequent(a):
    c = Counter(a)
    best = max(c.values())
    return min(x for x, k in c.items() if k == best)


TASKS = []


def task(**kw):
    TASKS.append(kw)


# ---------------------------------------------------------------- level I
task(
    key="EXP-I-1", level="I", topic="1.4", kcs=["int.arith", "cond.if_else"],
    features=dict(knowledge_actions=0, algorithm_freedom=0, edge_cases=1, justification=0),
    rationale="Бір шартты оператор және % амалы; шеттік жағдай — теріс сандар мен нөл.",
    title="Жұп немесе тақ",
    statement="Берілген n бүтін санының жұп немесе тақ екенін анықтаңыз.",
    input="Бір жолда бүтін n саны берілген (−10^9 ≤ n ≤ 10^9).",
    output="n жұп болса `EVEN`, тақ болса `ODD` сөзін шығарыңыз.",
    tests=[(f"{n}\n", odd_even(n) + "\n") for n in [4, 7, 0, -3, -8, 1, 1000000000, -999999999]],
    solution="""#include <iostream>
using namespace std;

int main() {
    long long n;
    cin >> n;
    cout << (n % 2 == 0 ? "EVEN" : "ODD") << "\\n";
    return 0;
}
""",
)

three = [(1, 2, 3), (3, 2, 1), (2, 3, 1), (5, 5, 5), (-1, -2, -3), (7, 7, 2),
         (-1000000000, 1000000000, 0), (0, 0, -1)]
task(
    key="EXP-I-2", level="I", topic="1.4", kcs=["cond.if_else", "cond.nested"],
    features=dict(knowledge_actions=0, algorithm_freedom=0, edge_cases=1, justification=0),
    rationale="Шартты оператормен үш санды салыстыру; шеттік жағдай — тең сандар мен теріс сандар.",
    title="Үш санның ең үлкені",
    statement="Берілген үш санның ең үлкенін анықтаңыз.",
    input="Бір жолда бос орынмен бөлінген үш бүтін сан a, b, c берілген (−10^9 ≤ a, b, c ≤ 10^9).",
    output="Үш санның ең үлкенін шығарыңыз.",
    tests=[(f"{a} {b} {c}\n", f"{max(a, b, c)}\n") for a, b, c in three],
    solution="""#include <iostream>
using namespace std;

int main() {
    long long a, b, c;
    cin >> a >> b >> c;
    long long best = a;
    if (b > best) best = b;
    if (c > best) best = c;
    cout << best << "\\n";
    return 0;
}
""",
)

task(
    key="EXP-I-3", level="I", topic="1.5", kcs=["while.loop", "while.digits", "int.arith"],
    features=dict(knowledge_actions=1, algorithm_freedom=0, edge_cases=1, justification=0),
    rationale="while циклі мен / және % амалдары; шеттік жағдай — n = 0 және соңындағы нөлдер.",
    title="Цифрларды кері шығару",
    statement="Берілген n бүтін санының цифрларын кері ретпен шығарыңыз.",
    input="Бір жолда бүтін n саны берілген (0 ≤ n ≤ 10^9).",
    output=("n санының цифрларын соңғысынан бастап бір жолға бос орынсыз шығарыңыз. "
            "Нөлдер де шығарылады: n = 120 болса, жауап `021`."),
    tests=[(f"{n}\n", f"{str(n)[::-1]}\n") for n in [12345, 7, 0, 120, 1000000000, 909, 11]],
    solution="""#include <iostream>
using namespace std;

int main() {
    long long n;
    cin >> n;
    if (n == 0) {
        cout << 0 << "\\n";
        return 0;
    }
    while (n > 0) {
        cout << n % 10;
        n /= 10;
    }
    cout << "\\n";
    return 0;
}
""",
)

# ---------------------------------------------------------------- level II
arrays = [[1, 2, 3, 4, 5], [2, 4, 6], [-3, -2, 7], [0], [1000000000 - 1] * 5,
          [rng.randint(-10**9, 10**9) for _ in range(1000)]]
task(
    key="EXP-II-4", level="II", topic="1.7", kcs=["array.vector", "array.traverse", "cond.if_else"],
    features=dict(knowledge_actions=1, algorithm_freedom=0, edge_cases=1, justification=1),
    rationale="Массив, цикл және шарт бірге; шеттік жағдай — теріс тақ сандар, қосындының int-тен асуы.",
    title="Тақ сандардың қосындысы",
    statement="Берілген массивтегі тақ сандардың қосындысын анықтаңыз.",
    input=("Бірінші жолда массив ұзындығы n берілген (1 ≤ n ≤ 10^5). Екінші жолда бос орынмен "
           "бөлінген n бүтін сан берілген, әрқайсысы −10^9-нан 10^9-ға дейін."),
    output="Массивтегі тақ сандардың қосындысын шығарыңыз. Тақ сан болмаса, 0 шығарыңыз.",
    tests=[(f"{len(a)}\n{' '.join(map(str, a))}\n", f"{sum(x for x in a if x % 2)}\n") for a in arrays],
    solution="""#include <iostream>
using namespace std;

int main() {
    int n;
    cin >> n;
    long long sum = 0;
    for (int i = 0; i < n; ++i) {
        long long x;
        cin >> x;
        if (x % 2 != 0) sum += x;
    }
    cout << sum << "\\n";
    return 0;
}
""",
)

words = ["level", "abca", "a", "ab", "aa", "racecar", "abcdba",
         "x" * 50000 + "y" + "x" * 49999, "x" * 49999 + "y" + "x" * 49999]
task(
    key="EXP-II-5", level="II", topic="1.10", kcs=["str.string", "array.traverse"],
    features=dict(knowledge_actions=1, algorithm_freedom=1, edge_cases=1, justification=1),
    rationale="Жол, цикл және салыстыру; тәсілді таңдау (екі көрсеткіш немесе кері жол); шешімді түсіндіру талап етіледі.",
    title="Палиндром сөз",
    statement="Берілген сөздің палиндром екенін анықтаңыз.",
    input="Бір жолда латынның кіші әріптерінен тұратын сөз берілген, ұзындығы 1-ден 10^5-ке дейін.",
    output="Сөз палиндром болса `YES`, болмаса `NO` шығарыңыз.",
    tests=[(f"{w}\n", ("YES" if is_pal(w) else "NO") + "\n") for w in words],
    solution="""#include <iostream>
#include <string>
using namespace std;

int main() {
    string s;
    cin >> s;
    size_t i = 0, j = s.size() - 1;
    bool palindrome = true;
    while (i < j) {
        if (s[i] != s[j]) {
            palindrome = false;
            break;
        }
        ++i;
        --j;
    }
    cout << (palindrome ? "YES" : "NO") << "\\n";
    return 0;
}
""",
)

task(
    key="EXP-II-6", level="II", topic="1.5", kcs=["while.loop", "int.arith"],
    features=dict(knowledge_actions=1, algorithm_freedom=1, edge_cases=1, justification=0),
    rationale="Цикл мен % амалы арқылы алгоритм құру; шеттік жағдай — n = 1, жай сан.",
    title="Санның бөлгіштері",
    statement="Берілген n натурал санының барлық бөлгіштерін анықтаңыз.",
    input="Бір жолда натурал n саны берілген (1 ≤ n ≤ 10^6).",
    output="n санының барлық бөлгіштерін өсу ретімен бір жолға бос орын арқылы шығарыңыз.",
    tests=[(f"{n}\n", " ".join(str(d) for d in range(1, n + 1) if n % d == 0) + "\n")
           for n in [12, 1, 7, 36, 1000000, 999983]],
    solution="""#include <iostream>
using namespace std;

int main() {
    int n;
    cin >> n;
    bool first = true;
    for (int d = 1; d <= n; ++d) {
        if (n % d == 0) {
            if (!first) cout << ' ';
            cout << d;
            first = false;
        }
    }
    cout << "\\n";
    return 0;
}
""",
)

# ---------------------------------------------------------------- level III
pal_cases = ["12321", "1231", "1123", "10", "1001", "2112", "100", "7", "1210", "122",
             "123456789987654321", "123456789987654312", "998", "9889", "112233"]
task(
    key="EXP-III-7", level="III", topic="1.10", kcs=["str.string", "map.frequency"],
    features=dict(knowledge_actions=1, algorithm_freedom=2, edge_cases=1, justification=1),
    rationale="Тәсіл берілмеген: сәйкес келмейтін жұптарды талдау немесе толық іріктеу; шеттік жағдай — алдыңғы нөл, бұрыннан палиндром.",
    title="Бір ауыстыру арқылы палиндром",
    statement=("Берілген санның кез келген екі цифрының орнын ауыстыру арқылы палиндром сан "
               "алуға болатынын анықтаңыз.\n\n"
               "Ең көбі бір рет екі цифрдың орнын ауыстыруға болады. Сан бұрыннан палиндром болса, "
               "жауап — иә. Алынған сан нөлден басталмауы керек."),
    input="Бір жолда натурал n саны берілген (1 ≤ n < 10^18), ол нөлден басталмайды.",
    output="Палиндром алуға болса `YES`, болмаса `NO` шығарыңыз.",
    tests=[(f"{s}\n", ("YES" if can_swap_pal(s) else "NO") + "\n") for s in pal_cases],
    solution="""#include <iostream>
#include <string>
#include <utility>
using namespace std;

bool isPalindrome(const string& s) {
    for (size_t i = 0, j = s.size() - 1; i < j; ++i, --j)
        if (s[i] != s[j]) return false;
    return true;
}

int main() {
    string s;
    cin >> s;
    bool ok = isPalindrome(s);
    for (size_t i = 0; i < s.size() && !ok; ++i) {
        for (size_t j = i + 1; j < s.size() && !ok; ++j) {
            swap(s[i], s[j]);
            if (s[0] != '0' && isPalindrome(s)) ok = true;
            swap(s[i], s[j]);
        }
    }
    cout << (ok ? "YES" : "NO") << "\\n";
    return 0;
}
""",
)

freq_cases = [[1, 2, 2, 3], [5], [3, 1, 3, 1], [-1, -1, 2, 2, -5],
              [rng.randint(1, 50) for _ in range(1000)],
              [rng.randint(-10**9, 10**9) for _ in range(200000)]]
task(
    key="EXP-III-8", level="III", topic="1.11", kcs=["map.map", "map.frequency"],
    features=dict(knowledge_actions=2, algorithm_freedom=1, edge_cases=2, justification=1),
    rationale="Жиілік құрылымын (map немесе сұрыптау) таңдау; n = 2·10^5 болғанда O(n^2) өтпейді; тең жиіліктер.",
    title="Ең жиі кездесетін сан",
    statement=("Берілген сандар жиынынан ең жиі кездесетін санды анықтаңыз.\n\n"
               "Бірнеше сан бірдей жиі кездессе, олардың ең кішісін шығарыңыз."),
    input=("Бірінші жолда n берілген (1 ≤ n ≤ 2·10^5). Екінші жолда бос орынмен бөлінген n бүтін "
           "сан берілген, әрқайсысы −10^9-нан 10^9-ға дейін."),
    output="Ең жиі кездесетін санды шығарыңыз.",
    tests=[(f"{len(a)}\n{' '.join(map(str, a))}\n", f"{most_frequent(a)}\n") for a in freq_cases],
    solution="""#include <iostream>
#include <map>
using namespace std;

int main() {
    int n;
    cin >> n;
    map<long long, int> count;
    for (int i = 0; i < n; ++i) {
        long long x;
        cin >> x;
        ++count[x];
    }
    long long best = 0;
    int bestCount = 0;
    for (const auto& [value, k] : count) {
        if (k > bestCount) {  // map is ordered, so ties keep the smallest value
            best = value;
            bestCount = k;
        }
    }
    cout << best << "\\n";
    return 0;
}
""",
)

next_cases = ["12543", "123", "321", "7", "115", "1999", "534976", "100", "987654321987654321",
              "111", "120"]
task(
    key="EXP-III-9", level="III", topic="1.12", kcs=["stl.sort", "str.string"],
    features=dict(knowledge_actions=2, algorithm_freedom=2, edge_cases=1, justification=1),
    rationale="Іздеу мен сұрыптауды байланыстырып тәсіл таңдау (next_permutation немесе қолмен); жауап жоқ жағдайы.",
    title="Келесі үлкен сан",
    statement=("Берілген санның цифрларының орнын ауыстыру арқылы бастапқы саннан үлкен ең кіші "
               "санды анықтаңыз.\n\nМысал: 12543 → 13245."),
    input="Бір жолда натурал n саны берілген (1 ≤ n < 10^18), ол нөлден басталмайды.",
    output="Ізделген санды шығарыңыз. Ондай сан болмаса, `-1` шығарыңыз.",
    tests=[(f"{s}\n", f"{next_greater(s)}\n") for s in next_cases],
    solution="""#include <algorithm>
#include <iostream>
#include <string>
using namespace std;

int main() {
    string s;
    cin >> s;
    if (next_permutation(s.begin(), s.end()))
        cout << s << "\\n";
    else
        cout << -1 << "\\n";
    return 0;
}
""",
)

for t in TASKS:
    d = OUT / t["key"]
    (d / "tests").mkdir(parents=True, exist_ok=True)
    (d / "statement.md").write_text(f"# {t['title']}\n\n{t['statement']}\n", encoding="utf-8")
    (d / "input.md").write_text(t["input"] + "\n", encoding="utf-8")
    (d / "output.md").write_text(t["output"] + "\n", encoding="utf-8")
    (d / "solution.cpp").write_text(t["solution"], encoding="utf-8")
    for i, (inp, out) in enumerate(t["tests"], start=1):
        (d / "tests" / f"{i:02d}.in").write_text(inp, encoding="utf-8")
        (d / "tests" / f"{i:02d}.out").write_text(out, encoding="utf-8")
    config = {
        "key": t["key"],
        "title": t["title"],
        "level": t["level"],
        "features": t["features"],
        "level_rationale": t["rationale"],
        "topic": t["topic"],
        "knowledge_components": t["kcs"],
        "time_limit_ms": 1000,
        "memory_limit_kb": 262144,
        "reference_language": "cpp17",
        "public_tests": ["01"],
        "source_note": ("Диссертация, Г қосымшасы. Кіріс-шығыс форматы, шектеулер, тесттер мен "
                        "эталон шешім — Claude Code жобасы, оқытушы бекітуі керек (Q-07)."),
    }
    (d / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    print(t["key"], len(t["tests"]), "tests")
