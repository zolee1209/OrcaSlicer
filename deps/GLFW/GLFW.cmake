if(BUILD_SHARED_LIBS)
    set(_build_shared ON)
    set(_build_static OFF)
else()
    set(_build_shared OFF)
    set(_build_static ON)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # Use X11 backend so CLI thumbnail rendering works on X11 sessions without
    # a Wayland compositor.  Wayland-only builds cause glfwInit() to fail when
    # WAYLAND_DISPLAY is not set (headless / X11-only environments).
    set(_glfw_use_wayland "-DGLFW_USE_WAYLAND=OFF")
else()
    set(_glfw_use_wayland "-DGLFW_USE_WAYLAND=OFF")
endif()

orcaslicer_add_cmake_project(GLFW
    URL https://github.com/glfw/glfw/archive/refs/tags/3.3.7.zip
    URL_HASH SHA256=e02d956935e5b9fb4abf90e2c2e07c9a0526d7eacae8ee5353484c69a2a76cd0
    #DEPENDS dep_Boost
    CMAKE_ARGS
        -DBUILD_SHARED_LIBS=${_build_shared} 
        -DGLFW_BUILD_DOCS=OFF
        -DGLFW_BUILD_EXAMPLES=OFF
	-DGLFW_BUILD_TESTS=OFF
	${_glfw_use_wayland}
)

if (MSVC)
    add_debug_dep(dep_GLFW)
endif ()
