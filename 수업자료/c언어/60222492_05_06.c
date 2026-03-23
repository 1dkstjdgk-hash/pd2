#include <stdio.h>
void main(){
	int num,result;
	printf("정수를 입력하시오:");
	scanf("%d",&num);
	result = num<20||num>80;
	printf("입력한 정수%d의 논리 연산결과:%d",num,result);
}
