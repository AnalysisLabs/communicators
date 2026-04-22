// manifest.cpp
#include <iostream>
#include <string>
#include <stacktrace>
#include <chrono>
#include <filesystem>
#include <pybind11/pybind11.h>
#include <string>

void manifest_printer(const std::string& msg) {
    std::cout << "[PRINTER] " << msg << std::endl;
}

void manifest_info(const std::string& msg) {
    std::cout << "[INFO] " << msg << std::endl;
}

void manifest_log() {}

namespace py = pybind11;

std::string get_cpp_stack() {
    std::string stack_str;
    auto st = std::stacktrace::current();
    for (const auto& frame : st) {
        stack_str += frame.to_string() + "\n";
    }
    return stack_str;
}

std::string get_timestamp() {
    auto now = std::chrono::system_clock::now();
    return std::format("{:%Y-%m-%d %H:%M:%S}", now);
}

std::string get_process_path(char* argv0) {
    return std::filesystem::path(argv0).lexically_normal().string();
}

py::object get_py_stack() {
    py::module inspect = py::module::import("inspect");
    py::object frame = py::module::import("inspect").attr("currentframe")().attr("f_back").attr("f_back");
    return inspect.attr("currentframe")();
}

//In communicators_core.cpp, modify Manifest::info:

void Manifest::info(const std::string& msg) {
    std::string prefix = get_timestamp() + " " + get_process_path(argv[0]) + " " + get_cpp_stack();  // For Python stacks, call get_py_stack() in pybind context
    manifest_info(prefix + " " + msg);
}
