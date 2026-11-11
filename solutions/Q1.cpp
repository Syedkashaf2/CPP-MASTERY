#include <algorithm>
#include <iostream>
#include <vector>
using namespace std;

int longestOnesWithAtMostKZeros(const vector<int> &nums, int k)
{
    int left{};
    int k_count{};
    int max_len{};

    for (int i = 0; i < static_cast<int>(nums.size()); i++)
    {
        if (nums.at(i) == 0)
        {
            k_count++;
        }

        while (k_count > k)
        {
            if (nums.at(left) == 0)
            {
                k_count--;
            }
            left++;
        }

        max_len = max(max_len, i - left + 1);
    }

    return max_len;
}

int main()
{
    vector<int> nums = {0, 0, 1, 1};
    int k = 1;
    cout << longestOnesWithAtMostKZeros(nums, k) << '\n'; // Output: 3
    return 0;
}