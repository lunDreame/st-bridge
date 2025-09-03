[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# ST Bridge
SmartThings bridge for HA

## 기여
문제가 있나요? [Issues](https://github.com/lunDreame/st-bridge/issues) 탭에 작성해 주세요.

- 더 좋은 아이디어가 있나요? [Pull requests](https://github.com/lunDreame/st-bridge/pulls)로 공유해 주세요!
- 이 통합을 사용하면서 발생하는 문제에 대해서는 책임지지 않습니다.

도움이 되셨나요? [카카오페이](https://qr.kakaopay.com/FWDWOBBmR)

## 준비
1. 스마트싱스 허브가 필요합니다.
2. 스마트싱스 허브에 [ST Bridge]() 엣지 드라이버가 설치되어 있어야 합니다.

## 설치
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lunDreame&repository=st-bridge&category=Integration)

이 통합을 설치하려면 이 GitHub Repo를 HACS Custom Repositories에 추가하거나 위의 배지를 클릭하세요. 설치 후 HomeAssistant를 재부팅하세요.

1. **기기 및 서비스** 메뉴에서 **통합 구성요소 추가하기**를 클릭합니다.
2. **브랜드 이름 검색** 탭에 `ST Bridge`을 입력하고 검색 결과에서 클릭합니다.
3. 아래 설명에 따라 설정을 진행합니다:
    - TCP 포트: 브리지 서버용 포트 (기본값: 8323)
4. 설정이 완료된 후, 컴포넌트가 로드되면 생성된 기기를 사용하실 수 있습니다.

이후 컴포넌트 옵션에서 스마트싱스에 노출할 엔티티를 선택할 수 있습니다.
현재는 `light`, `switch`, `fan`, `climate` 도메인을 지원합니다.

## 디버깅
문제 파악을 위해 아래 코드를 `configuration.yaml` 파일에 추가 후 HomeAssistant를 재시작해 주세요.

```yaml
logger:
  default: info
  logs:
    custom_components.st_bridge: debug
```

## 라이선스
ST Bridge 통합은 MIT 라이선스를 따릅니다.