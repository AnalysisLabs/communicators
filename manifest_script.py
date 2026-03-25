import re
import os

# Transforms print and _logger calls to manifest. equivalents.
def replace_logs_in_file(filepath):
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace print with manifest.printer
        content = re.sub(r'\bprint\(', 'manifest.printer(', content)

        # Replace _logger.<level> with manifest.<lowercase_level>, scrubbing prefixes
        def replace_logger(match):
            level = match.group(2).lower()
            return f'manifest.{level}('
        content = re.sub(r'(\w+\.)*_logger\.(\w+)\(', replace_logger, content)

        # Messages remain untouched
        output_path = filepath
        # output_path = os.path.splitext(filepath)[0] + '_new' + os.path.splitext(filepath)[1]
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f'Error processing {filepath}: {e}')
    return output_path

# Removes [ ] prefixes from messages in manifest. calls.
def scrub_messages_in_file(new_path):
    if not os.path.exists(new_path):
        return
    try:
        with open(new_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Split file into lines.
        lines = content.splitlines()
        updated_lines = []
        for line in lines:
            # Target manifest lines.
            if 'manifest.' in line or 'manifest(' in line:
                match = re.search(r'manifest[.(].*?\((.*?)\)', line, re.DOTALL)
                if match:
                    message = match.group(1)
                    # Detect [ after optional f or quote.
                    if re.match(r'\s*(f)?\s*["\']\s*\[', message):
                        print("Hello", message)
                        # Scrub [ ] while keeping prefix.
                        scrubbed_message = re.sub(r'^\s*(f?["\'])?\s*\[.*?\]\s*', r'\1', message)
                        print("helllo2", scrubbed_message)
                        line = line.replace(message, scrubbed_message)
            updated_lines.append(line)
        with open(new_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(updated_lines))
    except Exception as e:
        print(f'Error processing {new_path}: {e}')

files = ['/home/guatamap/Analysis Labs/Wrappers/wrapperFront5.py', '/home/guatamap/Analysis Labs/Wrappers/submit_builder.py', '/home/guatamap/Analysis Labs/Wrappers/proxy_server.py', '/home/guatamap/analysis-labs-website/website/edge/python_edge.py', '/home/guatamap/analysis-labs-website/website/app_backend/backend.py']

for file in files:
    new_path = replace_logs_in_file(file)
    scrub_messages_in_file(new_path)

