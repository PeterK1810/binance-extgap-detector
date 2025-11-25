{ pkgs }: {
  deps = [
    # Python 3.11 runtime
    pkgs.python311
    pkgs.python311Packages.pip

    # Optional: Development tools
    pkgs.python311Packages.virtualenv

    # Process manager for production deployment
    pkgs.python311Packages.supervisor
  ];

  # Environment setup
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      # Add any additional library dependencies here if needed
    ];
  };
}
