import lorem
import os
import nanoid
import shutil


#
# Generate test files under the parent dummy_files directory.
# Create the following directory structure:
# dummy_files/
# ├── common
# │   ├── test
# │   ├── src
# │   └── utils
# ├── src
# │   ├── component001
# │   ├── component002
# │   └── component003
# └── test
#     ├── component001
#     ├── component002
#     └── component003
#
# Under each component directory, create 500 text files with random content.

file_count = 50
component_count = 20
paragraphs = 100

def generate_test_files():
    # Create the directory structure
    base_dir = "dummy_files"

    component_dirs = [ f"component{str(i).zfill(3)}" for i in range(1, component_count + 1) ]

    shutil.rmtree(base_dir, "common")
    shutil.rmtree(base_dir, "src")
    shutil.rmtree(base_dir, "test")

    os.makedirs(os.path.join(base_dir, "common", "test"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "common", "src"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "common", "utils"), exist_ok=True)

    for component in component_dirs:
        os.makedirs(os.path.join(base_dir, "src", component), exist_ok=True)
        os.makedirs(os.path.join(base_dir, "test", component), exist_ok=True)

    # Generate 500 text files with random content in each component directory
    for component in component_dirs:
          for i in range(file_count):
            file_name = f"{nanoid.generate(size=6)}.txt"
            file_path = os.path.join(base_dir, "src", component, file_name)
            with open(file_path, 'w') as f:
                f.write(generate_text())
            file_path = os.path.join(base_dir, "test", component, file_name)
            with open(file_path, 'w') as f:
                f.write(generate_text())
            file_path = os.path.join(base_dir, "common", "test", file_name)
            with open(file_path, 'w') as f:
                f.write(generate_text())
            file_path = os.path.join(base_dir, "common", "src", file_name)
            with open(file_path, 'w') as f:
                f.write(generate_text())
            file_path = os.path.join(base_dir, "common", "utils", file_name)
            with open(file_path, 'w') as f:
                f.write(generate_text())
    print(f"Generated test files in {base_dir}", flush=True)

def generate_text():
    return '\n\n'.join(lorem.paragraph() for _ in range(paragraphs))


if __name__ == "__main__":
    generate_test_files()
