// event.hpp                                                          -*-C++-*-

#ifndef INCLUDED_UTILS_EVENT_HPP
#define INCLUDED_UTILS_EVENT_HPP

#include <utils/function.hpp>
#include <deque>

// -----------------------------------------------------------------------------

namespace utils
{
template <typename Signature>
class event;

template <typename...T>
class event<void(T...)>
{
  public:
    template <typename Functor>
    event& operator+=(Functor functor)
    {
        functions_.push_back(function<void(T...)>(functor));
        return *this;
    }

    void operator()(T...a) const
    {
        for (const auto &f : functions_) {
            f(a...);
        }
    }

    operator bool() const
    {
        return !functions_.empty();
    }

private:
    std::deque<function<void(T...)>> functions_;
};

// This allows using decltype(function pointer) as the type parameter.
template <typename R, typename...T>
class event<R(*)(T...)> : public event<void(T...)>
{
};

// This allows using decltype(method pointer) as the type parameter.
template <typename R, typename C, typename...T>
class event<R(C::*)(T...)> : public event<void(T...)>
{
};
}

#endif

// ----------------------------------------------------------------------------
// Copyright (C) 2014 Bloomberg Finance L.P.
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to
// deal in the Software without restriction, including without limitation the
// rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
// sell copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
// FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
// IN THE SOFTWARE.
// ----------------------------- END-OF-FILE ----------------------------------
