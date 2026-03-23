#include <stdio.h>
void main(){
	double aa,point;
	printf("백화점 결제액을 입력하시오:");
	scanf("%lf",&aa);
	point = 0.05*aa;
	printf("당신의 멤버십 포인트는%lf점입니다.",point);
}
