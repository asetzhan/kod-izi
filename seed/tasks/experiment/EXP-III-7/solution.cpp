#include <iostream>
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
    cout << (ok ? "YES" : "NO") << "\n";
    return 0;
}
