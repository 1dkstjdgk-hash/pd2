#include <stdio.h>
main(){
	float sight;
	int bld;
	printf("당신의 시력과 혈압을 입력하세요:");
	scanf("%f %d",&sight,&bld);
	printf("당신의 시력은 %f입니다.\n",sight);
	printf("당신의 혈압은 %d입니다.",bld); 
}
