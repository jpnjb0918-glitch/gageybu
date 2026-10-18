/* 우리집 가계부 (윈도우판) 실행기
 *
 * 같은 폴더의 runtime\python312.dll 을 불러 "python -m gagyebu" 와 같게 실행한다.
 *  - 창 프로그램(GUI)이라 검은 콘솔 창이 뜨지 않는다.
 *  - 명령줄 인자(예: --import-from 폴더)는 그대로 넘긴다.
 *  - 파이썬 경로는 runtime\python312._pth 가 정한다 (다른 파이썬 설치와 섞이지 않음).
 *
 * 만들기: x86_64-w64-mingw32-gcc -municode -mwindows -O2 launcher.c launcher.res -o 우리집가계부.exe
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdlib.h>
#include <wchar.h>

typedef int (*PyMainFn)(int, wchar_t **);

#define PATHMAX 32768
static wchar_t exe[PATHMAX], dir[PATHMAX], rt[PATHMAX], dll[PATHMAX];

static int fail(const wchar_t *msg)
{
    MessageBoxW(NULL, msg, L"우리집 가계부", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmdline, int show)
{
    (void)inst; (void)prev; (void)cmdline; (void)show;

    DWORD n = GetModuleFileNameW(NULL, exe, PATHMAX);
    if (n == 0 || n >= PATHMAX)
        return fail(L"실행 파일 위치를 알 수 없습니다.");
    wcscpy(dir, exe);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = L'\0';
    _snwprintf(rt, PATHMAX, L"%ls\\runtime", dir);
    _snwprintf(dll, PATHMAX, L"%ls\\python312.dll", rt);

    /* 표준 입출력 핸들이 쓸 수 없는 것이면 비워 둔다 (파이썬이 sys.stdout 등을 None 으로 두고 시작하게).
       파이썬 DLL 을 부르기 전에 해야 C 런타임이 비어 있는 상태로 시작한다. */
    static const DWORD std_ids[3] = {STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE};
    for (int i = 0; i < 3; i++) {
        HANDLE h = GetStdHandle(std_ids[i]);
        if (h == NULL || h == INVALID_HANDLE_VALUE)
            continue;
        SetLastError(NO_ERROR);
        if (GetFileType(h) == FILE_TYPE_UNKNOWN && GetLastError() != NO_ERROR)
            SetStdHandle(std_ids[i], NULL);
    }

    SetDllDirectoryW(rt);
    HMODULE py = LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!py)
        return fail(L"runtime\\python312.dll 을 불러오지 못했습니다.\n프로그램을 다시 설치해 주세요.");
    PyMainFn py_main = (PyMainFn)(void *)GetProcAddress(py, "Py_Main");
    if (!py_main)
        return fail(L"python312.dll 에서 Py_Main 을 찾지 못했습니다.");

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    wchar_t **args = calloc((size_t)argc + 4, sizeof(wchar_t *));
    if (!argv || !args)
        return fail(L"메모리가 부족합니다.");
    int k = 0;
    args[k++] = exe;
    args[k++] = L"-m";
    args[k++] = L"gagyebu";
    for (int i = 1; i < argc; i++)
        args[k++] = argv[i];
    args[k] = NULL;
    return py_main(k, args);
}
