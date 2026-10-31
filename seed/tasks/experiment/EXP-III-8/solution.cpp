#include <iostream>
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
    cout << best << "\n";
    return 0;
}
