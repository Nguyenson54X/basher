# Basher

Basher is a CLI AI Agent that interacts with the OpenAI model for executing and generating responses based on user input.

## Installation

To use Basher, ensure you have Python 3 installed along with the required dependencies. You can install the necessary packages using pip:

```bash
pip install openai
```

## Usage

To run Basher, you'll need to set a few environment variables prior to execution:

### Environment Variables

- `BASHER_API_ENDPOINT`: (optional) The API endpoint for the OpenAI-compatible LLM service. Default is `https://openrouter.ai/api/v1/`.
- `BASHER_API_KEY`: (required) Your API key for authenticating with the LLM service.
- `BASHER_MODEL`: (optional) The model to use for interaction. Default is `openai/gpt-4o-mini`.

### Command Line Arguments

You can run the Basher CLI from your terminal like this:

```bash
export BASHER_API_KEY='your_api_key_here'
python basher.py 'finish the coding task described in `TASK.md`'
```

## License

```
The MIT License

Copyright (c) 2026 Mistivia <i@mistivia.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
