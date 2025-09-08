import json
import sys
 
def main():
    try:
        input_text = sys.stdin.read().strip()
 
        full_body = "## Reviewed by AI:\n\n" + input_text
 
        data = {
            "body": full_body
        }
    
        formatted_json = json.dumps(data, ensure_ascii=False)
 
        print(formatted_json)
        return formatted_json
 
    except Exception as e:
        print(json.dumps({
            "error": str(e)
        }))
 
if __name__ == "__main__":
    main()
