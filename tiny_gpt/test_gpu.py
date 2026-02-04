import torch

print(f"PyTorch version: {torch.__version__}")

# Check for Intel XPU
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    print(f"Intel GPU (XPU) available: True")
    print(f"Device name: {torch.xpu.get_device_name(0)}")
    
    # Test computation
    x = torch.randn(1000, 1000).to('xpu')
    y = torch.randn(1000, 1000).to('xpu')
    z = x @ y
    print("GPU computation test: SUCCESS")
else:
    print("No Intel GPU detected")