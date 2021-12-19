# Ariston NET remotethermo integration for Home Assistant
This integration inspired by chomupashchuk fantastic work https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2
But it does not use Ariston website. It uses Ariston API what I reversed engineered.


| [This integration](https://github.com/fustom/ariston-remotethermo-home-assistant-v3)  | [Chomupashchuk's v2 integration](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2) |
| ------------- | ------------- |
| Uses real API  | Uses Ariton website  |
| Fast set/get data  | Sometimes needs minutes to set/get data |
| Easy to setup with UI | Not so easy to setup (only with configuration.yaml) |
| Integration & devices & entites | Only entites |
| Proper asynchronous integration, clean code | Hard to understand and maintain (ariston.py has more than 4000 lines) |
| Less sensors, switches, etc |  More sensors, switches, etc |
| New code, may contains lot of bugs | Old, tested code |

## TODO
- Localization. Currently only english is supported.
- More sensors, switches, binary sersors, selectors, services.
- Energy.
- Exception handling.
- More logs.
- Unit tests.
- Fun.

## Integration was tested on and works with:
- Ariston Alteas One 24

I only have one Ariston Alteas One with only one zone, but feel free to test something else and create new issue / pull request if something goes wrong.

## Installation
Copy ariston folder to your configuration/custom_components path or use hacs custom repositories.
Use the add integration UI to set up your device.

![Kazam_screenshot_00003](https://user-images.githubusercontent.com/6751243/146653448-ff7b6f9d-cbf1-4555-9a75-61bf68bc9d3e.png)

![Kazam_screenshot_00004](https://user-images.githubusercontent.com/6751243/146653484-52e39d78-7c6f-44ae-888d-acf246147290.png)

![Kazam_screenshot_00005](https://user-images.githubusercontent.com/6751243/146653512-373d67d2-dcff-4a58-9a1c-022613f6702f.png)

![Kazam_screenshot_00006](https://user-images.githubusercontent.com/6751243/146653543-d12ea409-3f8e-4387-bfcc-16dbc393dbb5.png)

![Kazam_screenshot_00008](https://user-images.githubusercontent.com/6751243/146653616-3bb5de96-b51d-4579-bf88-c7835a2e48e8.png)![Kazam_screenshot_00009](https://user-images.githubusercontent.com/6751243/146657797-ed14b741-595a-48a6-9126-1acca3beb69f.png)


## Peace Love Freedom
