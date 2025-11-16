{ pkgs }: {
  deps = [
    # Python 3.11 runtime
    pkgs.python311
    pkgs.python311Packages.pip

    # Optional: Development tools
    pkgs.python311Packages.virtualenv
  ];

  # Environment setup
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      # Add any additional library dependencies here if needed
    ];
  };
}
