import os
import shutil

def clear_folder(folder_path):
    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)  # Remove file or link
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)  # Remove folder
            print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

# Replace these with your actual folder paths
folder_1 = r"/home/nifi/nifi2/users/priyanshu/Output/Output1"
folder_2 = r"/home/nifi/nifi2/users/priyanshu/Output/Output2"
folder_3 = r"/home/nifi/nifi2/users/priyanshu/Output/Output3"
folder_4 = r"/home/nifi/nifi2/users/priyanshu/Output/Output4"

clear_folder(folder_1)
clear_folder(folder_2)
clear_folder(folder_3)
clear_folder(folder_4)
