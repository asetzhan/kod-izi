#include <iostream>
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
    cout << (palindrome ? "YES" : "NO") << "\n";
    return 0;
}
