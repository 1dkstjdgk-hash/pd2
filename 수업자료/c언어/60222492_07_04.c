#include <stdio.h>
void main(){
	int month;
	printf("월을 입력하시오(1~12):");
	scanf("%d",&month);
	if(month>=1&&month<=3)
	printf("1사분기입니다.");
	else if(month>=4&&month<=6)
	printf("2사분기입니다.");
	else if(month>=7&&month<=9)
	printf("3사분기입니다.");
	else if(month>=10&&month<=12)
	printf("4사분기입니다.");
	else
	printf("잘못 입력하였습니다.");
}
